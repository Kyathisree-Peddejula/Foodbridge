"""Weeks 5-6: surplus listings, AI matching and pickup scheduling - lifecycle and edge cases."""
from datetime import timedelta

from django.core import mail

from marketplace.models import Match, NGORequirement, Pickup, SurplusListing
from marketplace.services import send_reminders

from .base import TODAY, FBTestCase, iso, later


class ListingMixin:
    def listing(self, kg=20, days=1, slug="cooked-meals", fridge=False, **kw):
        body = {"title": kw.pop("title", "Veg biryani trays"), "quantity_kg": kg,
                "expiry_date": str(TODAY() + timedelta(days=days)), "category": self.cat[slug].id,
                "requires_refrigeration": fridge,
                "windows": [{"start": iso(later(1)), "end": iso(later(5))}], **kw}
        r = self.api(self.u_biz).post("/api/marketplace/listings/", body, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def claim(self, listing, user=None, kg=5, **kw):
        body = {"quantity_kg": kg, **kw}
        if "scheduled_start" not in kw:
            body.setdefault("window", listing["windows"][0]["id"])
        return self.api(user or self.u_ngo).post(f"/api/marketplace/listings/{listing['id']}/claim/", body, format="json")


class ListingValidationTests(ListingMixin, FBTestCase):
    def post(self, **kw):
        body = {"title": "Rice", "quantity_kg": 5, "expiry_date": str(TODAY() + timedelta(days=2)), **kw}
        return self.api(self.u_biz).post("/api/marketplace/listings/", body, format="json")

    def test_invalid_inputs(self):
        self.assertEqual(self.post(quantity_kg=0).status_code, 400)
        self.assertEqual(self.post(expiry_date=str(TODAY() - timedelta(days=1))).status_code, 400)
        self.assertEqual(self.post(windows=[{"start": iso(later(3)), "end": iso(later(1))}]).status_code, 400)
        self.assertEqual(self.post(windows=[{"start": iso(later(-5)), "end": iso(later(-3))}]).status_code, 400)
        self.assertEqual(self.post(dietary_tags=["carnivore"]).status_code, 400)
        late = [{"start": iso(later(days=4)), "end": iso(later(2, days=4))}]           # after best-before
        self.assertEqual(self.post(windows=late).status_code, 400)

    def test_default_window_and_auto_category(self):
        r = self.post(title="Fresh bananas")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(r.json()["windows"]), 1)
        self.assertEqual(r.json()["category_detail"]["slug"], "fruits")

    def test_ngo_cannot_create_listing(self):
        body = {"title": "x", "quantity_kg": 1, "expiry_date": str(TODAY())}
        self.assertEqual(self.api(self.u_ngo).post("/api/marketplace/listings/", body, format="json").status_code, 403)

    def test_from_batch_rules(self):
        b = self.stock(qty=10, days=1)
        c = self.api(self.u_biz)
        r = c.post("/api/marketplace/listings/from-batch/", {"batch": b.id, "quantity": 4}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["quantity_kg"], 4)
        dup = c.post("/api/marketplace/listings/from-batch/", {"batch": b.id}, format="json")
        self.assertEqual(dup.status_code, 400)
        expired = self.stock(qty=3, days=-1, name="Old", sku="OLD")
        self.assertEqual(c.post("/api/marketplace/listings/from-batch/", {"batch": expired.id}, format="json").status_code, 400)


class MatchingTests(ListingMixin, FBTestCase):
    def test_closer_ngo_ranks_higher_and_far_is_excluded_by_range(self):
        NGORequirement.objects.create(ngo=self.ngo_far, title="Anything", max_distance_km=100)
        l = self.listing()
        m = self.api(self.u_biz).get(f"/api/marketplace/listings/{l['id']}/matches/").json()
        names = [x["ngo"]["name"] for x in m]
        self.assertEqual(names[0], "Near NGO")
        self.assertIn("Far NGO", names)
        # tighten the far NGO's range → hard constraint removes it
        NGORequirement.objects.filter(ngo=self.ngo_far).update(max_distance_km=5)
        m = self.api(self.u_biz).get(f"/api/marketplace/listings/{l['id']}/matches/?refresh=1").json()
        self.assertNotIn("Far NGO", [x["ngo"]["name"] for x in m])

    def test_cold_chain_and_dietary_constraints(self):
        NGORequirement.objects.create(ngo=self.ngo, title="Veg only, no fridge", dietary_restrictions=["veg"],
                                      has_refrigeration=False)
        chilled = self.listing(slug="dairy", fridge=True, title="Milk crates")
        ids = [x["ngo"]["id"] for x in self.api(self.u_biz).get(f"/api/marketplace/listings/{chilled['id']}/matches/").json()]
        self.assertNotIn(self.ngo.id, ids)
        nonveg = self.listing(title="Chicken curry", dietary_tags=["non_veg"])
        ids = [x["ngo"]["id"] for x in self.api(self.u_biz).get(f"/api/marketplace/listings/{nonveg['id']}/matches/").json()]
        self.assertNotIn(self.ngo.id, ids)

    def test_category_need_boosts_score_and_breakdown_is_explained(self):
        NGORequirement.objects.create(ngo=self.ngo, title="Hot meals")
        r = NGORequirement.objects.create(ngo=self.ngo_far, title="Cooked meals", max_distance_km=100)
        r.categories.add(self.cat["cooked-meals"])
        l = self.listing()
        m = {x["ngo"]["name"]: x for x in self.api(self.u_biz).get(f"/api/marketplace/listings/{l['id']}/matches/").json()}
        self.assertEqual(m["Far NGO"]["breakdown"]["category"], 1.0)
        self.assertIn("_weights", m["Far NGO"]["breakdown"])
        self.assertAlmostEqual(sum(m["Far NGO"]["breakdown"]["_weights"].values()), 1.0, places=2)

    def test_feed_ranked_and_decline_hides(self):
        l = self.listing()
        c = self.api(self.u_ngo)
        feed = c.get("/api/marketplace/listings/feed/").json()
        self.assertEqual(feed[0]["id"], l["id"])
        self.assertIsNotNone(feed[0]["match_score"])
        c.post(f"/api/marketplace/listings/{l['id']}/decline/")
        self.assertNotIn(l["id"], [x["id"] for x in c.get("/api/marketplace/listings/feed/").json()])

    def test_matched_ngos_are_notified(self):
        self.listing()
        self.assertTrue(self.ngo.notifications.filter(kind="match").exists())


class PickupLifecycleTests(ListingMixin, FBTestCase):
    def test_full_lifecycle_updates_stock_and_impact(self):
        b = self.stock(qty=30, days=1, name="Veg pulao", slug="cooked-meals", unit="kg", sku="PUL")
        c = self.api(self.u_biz)
        l = c.post("/api/marketplace/listings/from-batch/", {"batch": b.id, "quantity": 12}, format="json").json()
        p = self.claim(l, kg=12).json()
        self.assertEqual((p["status"], p["awaiting"]), ("requested", "donor"))
        self.assertEqual(c.get(f"/api/marketplace/listings/{l['id']}/").json()["status"], "reserved")
        p = c.post(f"/api/pickups/{p['id']}/confirm/").json()
        self.assertEqual(p["status"], "confirmed")
        ngo = self.api(self.u_ngo)
        p = ngo.post(f"/api/pickups/{p['id']}/collect/", {"driver_name": "Ravi"}, format="json").json()
        self.assertEqual(p["status"], "in_transit")
        b.refresh_from_db()
        self.assertEqual(b.quantity, 18)
        p = ngo.post(f"/api/pickups/{p['id']}/complete/", {"quantity_received_kg": 12, "beneficiaries_served": 30},
                     format="json").json()
        self.assertEqual((p["status"], p["meals_served"]), ("completed", int(12 / 0.42)))
        impact = c.get("/api/analytics/impact/?scope=mine").json()
        self.assertEqual(impact["food_diverted_kg"], 12)
        self.assertAlmostEqual(impact["co2e_avoided_kg"], 12 * self.cat["cooked-meals"].co2e_per_kg, places=1)
        self.assertEqual(c.get(f"/api/marketplace/listings/{l['id']}/").json()["status"], "completed")
        self.assertTrue(len(mail.outbox) > 0)            # confirmation e-mails went out

    def test_donor_offer_needs_ngo_confirmation(self):
        l = self.listing()
        p = self.api(self.u_biz).post(f"/api/marketplace/listings/{l['id']}/offer/",
                                      {"ngo": self.ngo.id, "quantity_kg": 5, "window": l["windows"][0]["id"]},
                                      format="json").json()
        self.assertEqual(p["awaiting"], "ngo")
        self.assertEqual(self.api(self.u_ngo).post(f"/api/pickups/{p['id']}/confirm/").json()["status"], "confirmed")

    def test_claim_edge_cases(self):
        l = self.listing(kg=10)
        self.assertEqual(self.claim(l, kg=11).status_code, 400)                       # more than available
        self.assertEqual(self.claim(l, kg=4).status_code, 201)
        self.assertEqual(self.claim(l, kg=1).status_code, 400)                        # duplicate open pickup
        self.assertEqual(self.claim(l, user=self.u_ngo_far, kg=7).status_code, 400)   # only 6 kg left
        other = self.listing(title="Other")
        r = self.claim(l, user=self.u_ngo_far, kg=1, window=other["windows"][0]["id"])
        self.assertEqual(r.status_code, 400)                                          # foreign window
        r = self.api(self.u_ngo_far).post(f"/api/marketplace/listings/{l['id']}/claim/", {"quantity_kg": 1}, format="json")
        self.assertEqual(r.status_code, 400)                                          # no slot given
        slot = {"scheduled_start": iso(later(-5)), "scheduled_end": iso(later(-4))}
        self.assertEqual(self.claim(l, user=self.u_ngo_far, kg=1, **slot).status_code, 400)   # in the past
        late = {"scheduled_start": iso(later(days=5)), "scheduled_end": iso(later(2, days=5))}
        self.assertEqual(self.claim(l, user=self.u_ngo_far, kg=1, **late).status_code, 400)   # after best-before

    def test_confirmation_and_completion_edge_cases(self):
        l = self.listing()
        p = self.claim(l).json()
        ngo, biz = self.api(self.u_ngo), self.api(self.u_biz)
        self.assertEqual(ngo.post(f"/api/pickups/{p['id']}/confirm/").status_code, 400)       # already confirmed
        self.assertEqual(ngo.post(f"/api/pickups/{p['id']}/collect/").status_code, 400)       # not scheduled yet
        biz.post(f"/api/pickups/{p['id']}/confirm/")
        r = ngo.post(f"/api/pickups/{p['id']}/complete/", {"quantity_received_kg": 50}, format="json")
        self.assertEqual(r.status_code, 400)                                                  # > collected
        self.assertEqual(Pickup.objects.get(pk=p["id"]).status, "confirmed")                  # no side effects
        ngo.post(f"/api/pickups/{p['id']}/complete/", {}, format="json")
        self.assertEqual(biz.post(f"/api/pickups/{p['id']}/cancel/", {}, format="json").status_code, 400)

    def test_outsider_cannot_act_on_pickup(self):
        p = self.claim(self.listing()).json()
        self.assertEqual(self.api(self.u_biz2).post(f"/api/pickups/{p['id']}/confirm/").status_code, 404)
        self.assertEqual(self.api(self.u_ngo_far).get(f"/api/pickups/{p['id']}/").status_code, 404)

    def test_reschedule_resets_confirmation(self):
        l = self.listing()
        p = self.claim(l).json()
        biz = self.api(self.u_biz)
        biz.post(f"/api/pickups/{p['id']}/confirm/")
        r = biz.post(f"/api/pickups/{p['id']}/reschedule/", {"scheduled_start": iso(later(3)),
                                                             "scheduled_end": iso(later(4))}, format="json").json()
        self.assertEqual((r["status"], r["awaiting"]), ("requested", "ngo"))

    def test_withdraw_listing_cancels_open_pickups(self):
        l = self.listing()
        p = self.claim(l).json()
        self.api(self.u_biz).post(f"/api/marketplace/listings/{l['id']}/cancel/")
        self.assertEqual(Pickup.objects.get(pk=p["id"]).status, "cancelled")
        self.assertIn(self.claim(l, user=self.u_ngo_far).status_code, (400, 404))

    def test_no_show_lowers_reliability(self):
        l = self.listing()
        p = self.claim(l).json()
        self.api(self.u_biz).post(f"/api/pickups/{p['id']}/confirm/")
        before = self.ngo.reliability_score
        self.api(self.u_biz).post(f"/api/pickups/{p['id']}/cancel/", {"no_show": True}, format="json")
        self.ngo.refresh_from_db()
        self.assertLess(self.ngo.reliability_score, before)

    def test_reminders_sent_once(self):
        l = self.listing()
        p = self.claim(l).json()
        self.api(self.u_biz).post(f"/api/pickups/{p['id']}/confirm/")
        self.assertEqual(send_reminders(), 1)
        self.assertEqual(send_reminders(), 0)

    def test_calendar(self):
        l = self.listing()
        self.claim(l)
        ev = self.api(self.u_ngo).get(f"/api/pickups/calendar/?start={TODAY()}&end={TODAY() + timedelta(days=2)}").json()
        self.assertEqual(len(ev["events"]), 1)
