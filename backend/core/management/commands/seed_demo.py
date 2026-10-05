"""
Create a complete demo world:
  * platform admin            admin@foodbridge.dev / Admin@12345
  * FreshRetailNet stores     store<ID>@foodbridge.dev / Demo@12345   (from the dataset)
  * restaurants & bakeries    hotel@ / bakery@ / spice@ / canteen@foodbridge.dev / Demo@12345
  * NGOs                      hope@ / annapoorna@ / greenhands@ / seva@ / cityrelief@foodbridge.dev / Demo@12345
  * listings, historical deliveries (for impact charts) and upcoming pickups
"""
import random
import sys
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Organization, User
from inventory.models import FoodCategory, InventoryBatch, StockTransaction
from inventory.services import get_or_create_product, receive_stock, run_expiry_scan
from inventory.taxonomy import ensure_taxonomy
from marketplace.models import AvailabilityWindow, NGORequirement, Pickup, SurplusListing
from marketplace.services import compute_matches

PW = "Demo@12345"
LAT, LNG = 12.9716, 77.5946

BUSINESSES = [
    ("Hotel Sunshine", "hotel", "hotel@foodbridge.dev", 0.012, 0.018, [
        ("Veg biryani", "cooked-meals", "portion", 0.35, 60, 1, 90),
        ("Dal tadka", "cooked-meals", "portion", 0.3, 45, 1, 60),
        ("Paneer butter masala", "cooked-meals", "portion", 0.3, 30, 0, 140),
        ("Garden salad", "prepared-deli", "portion", 0.25, 20, 1, 80)]),
    ("City Bakery", "bakery", "bakery@foodbridge.dev", -0.02, 0.01, [
        ("Whole wheat bread", "bakery", "pcs", 0.4, 80, 2, 35),
        ("Croissant", "bakery", "pcs", 0.08, 120, 1, 40),
        ("Chocolate muffin", "bakery", "pcs", 0.1, 90, 2, 30),
        ("Pav buns", "bakery", "pack", 0.3, 50, 1, 25)]),
    ("Spice Garden Restaurant", "restaurant", "spice@foodbridge.dev", 0.03, -0.025, [
        ("Chicken curry", "cooked-meals", "portion", 0.35, 35, 0, 180),
        ("Jeera rice", "cooked-meals", "portion", 0.3, 50, 1, 60),
        ("Gulab jamun", "sweets", "pcs", 0.05, 200, 3, 12)]),
    ("Campus Canteen", "canteen", "canteen@foodbridge.dev", -0.035, -0.03, [
        ("Rice and curry meal", "cooked-meals", "portion", 0.4, 100, 0, 50),
        ("Idli batter", "prepared-deli", "kg", 1.0, 25, 2, 70),
        ("Toned milk 1L", "dairy", "l", 1.03, 40, 3, 56),
        ("Banana", "fruits", "kg", 1.0, 30, 2, 50)]),
]
NGOS = [
    ("Hope Foundation", "ngo", "hope@foodbridge.dev", 0.005, 0.02, 1800, 400, ["cooked-meals", "prepared-deli"],
     "Hot meals for night shelters", ["veg", "non_veg"], True),
    ("Annapoorna NGO", "community_kitchen", "annapoorna@foodbridge.dev", -0.015, 0.005, 2400, 600,
     ["bakery", "grains", "vegetables", "cooked-meals"], "Breakfast program: bread, grains and vegetables",
     ["veg"], False),
    ("Green Hands", "food_bank", "greenhands@foodbridge.dev", 0.04, 0.03, 900, 350,
     ["fruits", "vegetables", "dairy"], "Fresh produce and dairy for families", [], True),
    ("Seva Trust", "shelter", "seva@foodbridge.dev", -0.04, -0.02, 700, 250, ["cooked-meals", "sweets"],
     "Cooked meals and desserts for elders", ["veg"], False),
    ("City Relief", "food_bank", "cityrelief@foodbridge.dev", 0.02, -0.04, 1200, 500, [],
     "Any safe surplus food, all categories", [], True),
]


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, p):
        p.add_argument("--stores", type=int, default=3)
        p.add_argument("--products", type=int, default=20)
        p.add_argument("--skip-dataset", action="store_true")

    def handle(self, *args, **o):
        rng = random.Random(11)
        ensure_taxonomy()
        cats = {c.slug: c for c in FoodCategory.objects.all()}
        tz = timezone.get_current_timezone()
        today = timezone.localdate()

        if not User.objects.filter(email="admin@foodbridge.dev").exists():
            User.objects.create_superuser("admin@foodbridge.dev", "admin@foodbridge.dev", "Admin@12345", role="admin")

        if not o["skip_dataset"]:
            ds = settings.DATASET_DIR / "train.parquet"
            if not ds.exists():
                self.stdout.write("Dataset parquet not found → generating a synthetic FreshRetailNet sample")
                sys.path.insert(0, str(settings.REPO_ROOT / "scripts"))
                from fetch_dataset import generate_synthetic
                tr, ev = generate_synthetic()
                ds.parent.mkdir(parents=True, exist_ok=True)
                tr.to_parquet(ds, index=False)
                ev.to_parquet(ds.parent / "eval.parquet", index=False)
            call_command("import_freshretail", stores=o["stores"], products=o["products"], stdout=self.stdout)

        businesses = []
        for name, kind, email, dlat, dlng, items in BUSINESSES:
            org, _ = Organization.objects.get_or_create(name=name, org_type="business", defaults=dict(
                kind=kind, city="Bengaluru", address=f"{name}, Bengaluru", contact_email=email, is_verified=True,
                latitude=round(LAT + dlat, 6), longitude=round(LNG + dlng, 6), phone="+91 80 4000 1000"))
            if not User.objects.filter(email=email).exists():
                User.objects.create_user(email, email, PW, role="business", organization=org, first_name=name.split()[0])
            for pname, slug, unit, w, daily, days_left, cost in items:
                prod, created = get_or_create_product(org, name=pname, category=cats[slug], unit=unit,
                                                      unit_cost=cost, unit_weight_kg=w)
                if created:
                    # 45 days of sales + occasional waste to feed forecasts and waste trends
                    txns = []
                    for d in range(45, 0, -1):
                        day = today - timedelta(days=d)
                        mult = 1.25 if day.weekday() >= 5 else 1.0
                        q = max(0, round(rng.gauss(daily * mult, daily * 0.2)))
                        txns.append(StockTransaction(organization=org, product=prod, txn_type="sale", quantity=q,
                                                     unit_price=cost * 1.6,
                                                     occurred_at=datetime.combine(day, time(20), tz), source="manual"))
                        if rng.random() < 0.35:
                            txns.append(StockTransaction(organization=org, product=prod, txn_type="waste",
                                                         quantity=round(daily * rng.uniform(0.05, 0.25)),
                                                         occurred_at=datetime.combine(day, time(22), tz),
                                                         source="manual", note="end of day discard"))
                    StockTransaction.objects.bulk_create(txns)
                    receive_stock(prod, round(daily * rng.uniform(1.2, 2.6)), expiry_date=today + timedelta(days=days_left))
            businesses.append(org)

        ngos = []
        for name, kind, email, dlat, dlng, benef, cap, cslugs, need, diet, fridge in NGOS:
            org, _ = Organization.objects.get_or_create(name=name, org_type="ngo", defaults=dict(
                kind=kind, city="Bengaluru", address=f"{name} Centre, Bengaluru", contact_email=email,
                latitude=round(LAT + dlat, 6), longitude=round(LNG + dlng, 6), beneficiaries=benef,
                daily_capacity_kg=cap, is_verified=True, phone="+91 80 5000 2000"))
            if not User.objects.filter(email=email).exists():
                User.objects.create_user(email, email, PW, role="ngo", organization=org, first_name=name.split()[0])
            if not org.requirements.exists():
                req = NGORequirement.objects.create(ngo=org, title=need, max_quantity_kg=cap, max_distance_km=15,
                                                    dietary_restrictions=diet, has_refrigeration=fridge,
                                                    notes=need, pickup_from_hour=7, pickup_to_hour=22)
                req.categories.set([cats[s] for s in cslugs])
            ngos.append(org)

        # historical completed deliveries (last ~5 months) for impact dashboards
        if not Pickup.objects.filter(status="completed").exists():
            for i in range(60):
                donor = rng.choice(businesses)
                ngo = rng.choice(ngos)
                cat = cats[rng.choice(["cooked-meals", "bakery", "fruits", "vegetables", "dairy", "grains",
                                       "prepared-deli"])]
                days_ago = rng.randint(1, 150)
                when = timezone.now() - timedelta(days=days_ago, hours=rng.randint(0, 6))
                kg = round(rng.uniform(8, 70), 1)
                l = SurplusListing.objects.create(
                    donor=donor, title=f"{cat.name} surplus", category=cat, quantity_kg=kg,
                    expiry_date=(when + timedelta(days=1)).date(), pickup_address=donor.address,
                    latitude=donor.latitude, longitude=donor.longitude, status="completed")
                SurplusListing.objects.filter(pk=l.pk).update(created_at=when - timedelta(hours=5))
                Pickup.objects.create(listing=l, ngo=ngo, quantity_kg=kg, scheduled_start=when,
                                      scheduled_end=when + timedelta(hours=1), status="completed",
                                      donor_confirmed_at=when, ngo_confirmed_at=when, picked_up_at=when,
                                      delivered_at=when + timedelta(hours=1), quantity_received_kg=kg,
                                      meals_served=int(kg / 0.42), beneficiaries_served=int(kg / 0.42 * 0.8))

        # live listings with matches + a few scheduled pickups
        if not SurplusListing.objects.filter(status="available").exists():
            base = timezone.now().replace(minute=0, second=0, microsecond=0)
            for b in InventoryBatch.objects.filter(organization__in=businesses, quantity__gt=0)[:8]:
                p = b.product
                kg = round(b.quantity * p.unit_weight_kg * 0.6, 1)
                if kg <= 0:
                    continue
                l = SurplusListing.objects.create(
                    donor=b.organization, batch=b, title=p.name, category=p.category, quantity_kg=kg,
                    quantity_units=round(b.quantity * 0.6, 1), unit=p.unit, expiry_date=max(b.expiry_date, today),
                    pickup_address=b.organization.address, latitude=b.organization.latitude,
                    longitude=b.organization.longitude,
                    dietary_tags=["non_veg"] if "chicken" in p.name.lower() else ["veg"],
                    requires_refrigeration=p.category.storage in ("chilled", "frozen"),
                    handling_notes=p.category.handling_notes)
                for k in range(2):
                    AvailabilityWindow.objects.create(listing=l, start=base + timedelta(hours=2 + 24 * k),
                                                      end=base + timedelta(hours=6 + 24 * k))
                b.status = "listed"
                b.save(update_fields=["status"])
                ranked = compute_matches(l)
                top = ranked.first()
                if top and rng.random() < 0.5:
                    w = l.windows.first()
                    Pickup.objects.create(listing=l, ngo=top.ngo, match=top, quantity_kg=round(kg / 2, 1),
                                          scheduled_start=w.start, scheduled_end=w.end,
                                          status=rng.choice(["requested", "confirmed"]),
                                          ngo_confirmed_at=timezone.now(),
                                          donor_confirmed_at=timezone.now() if rng.random() < 0.6 else None)
                    l.refresh_status()

        run_expiry_scan()
        self.stdout.write(self.style.SUCCESS(
            "Demo ready.\n  admin@foodbridge.dev / Admin@12345\n  hotel@foodbridge.dev / Demo@12345 (business)\n"
            "  hope@foodbridge.dev / Demo@12345 (NGO)\n  store<ID>@foodbridge.dev / Demo@12345 (dataset stores)"))
