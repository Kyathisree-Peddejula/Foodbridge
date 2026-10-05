"""Weeks 1-2: inventory input (manual, CSV, POS, scan), taxonomy and expiry tracking."""
from datetime import timedelta

from inventory.models import ExpiryAlert, ExpiryThreshold, InventoryBatch, POSIntegration, Product, StockTransaction
from inventory.services import consume_stock, run_expiry_scan

from .base import TODAY, FBTestCase


class ManualEntryTests(FBTestCase):
    def test_auto_classification_and_default_expiry(self):
        c = self.api(self.u_biz)
        r = c.post("/api/inventory/products/", {"name": "Fresh paneer cubes", "unit": "kg"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["category_detail"]["slug"], "dairy")
        b = c.post("/api/inventory/batches/", {"product": r.json()["id"], "quantity": 5}, format="json")
        self.assertEqual(b.status_code, 201, b.content)
        # no expiry given → received date + category shelf life
        self.assertGreater(b.json()["days_to_expiry"], 0)

    def test_rejects_other_tenants_product(self):
        foreign = self.product(org=self.biz2, name="Their milk")
        r = self.api(self.u_biz).post("/api/inventory/batches/", {"product": foreign.id, "quantity": 5}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(InventoryBatch.objects.filter(product=foreign).exists())

    def test_rejects_zero_quantity_and_expiry_before_receipt(self):
        p = self.product()
        c = self.api(self.u_biz)
        self.assertEqual(c.post("/api/inventory/batches/", {"product": p.id, "quantity": 0}, format="json").status_code, 400)
        r = c.post("/api/inventory/batches/", {"product": p.id, "quantity": 3, "received_date": str(TODAY()),
                                               "expiry_date": str(TODAY() - timedelta(days=2))}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_adjust_caps_at_on_hand_and_blocks_depleted(self):
        b = self.stock(qty=4)
        c = self.api(self.u_biz)
        r = c.post(f"/api/inventory/batches/{b.id}/adjust/", {"quantity": 10, "reason": "waste"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["quantity"], 0)
        self.assertEqual(r.json()["status"], "depleted")
        r = c.post(f"/api/inventory/batches/{b.id}/adjust/", {"quantity": 1, "reason": "waste"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_fifo_consumption(self):
        p = self.product()
        old = self.stock(qty=5, days=1, product=p)
        new = self.stock(qty=5, days=6, product=p)
        consume_stock(p, 7)
        old.refresh_from_db(), new.refresh_from_db()
        self.assertEqual((old.quantity, new.quantity), (0, 3))

    def test_sale_without_stock_is_still_recorded_for_demand_history(self):
        p = self.product()
        consume_stock(p, 3)
        self.assertEqual(StockTransaction.objects.filter(product=p, txn_type="sale").count(), 1)


class CSVUploadTests(FBTestCase):
    def upload(self, text, mode="inventory", encoding="utf-8"):
        return self.api(self.u_biz).post("/api/inventory/upload-csv/",
                                         {"file": self.csv(text, encoding=encoding), "mode": mode}, format="multipart")

    def test_good_and_bad_rows_are_reported_per_row(self):
        text = ("name,quantity,unit,expiry_date\n"
                "Whole milk,10,l,2099-01-01\n"
                "Bread,-2,pcs,2099-01-01\n"
                "Yogurt,3,kg,not-a-date\n"
                "Cheese,2,kg,2099-01-01\n")
        r = self.upload(text).json()
        self.assertEqual((r["rows_total"], r["rows_created"], r["rows_failed"]), (4, 2, 2))
        self.assertEqual([e["row"] for e in r["errors"]], [3, 4])

    def test_semicolon_and_windows_encoding(self):
        text = "product;qty;unit;best_before\nCrème fraîche;4;kg;01/01/2099\n"
        r = self.upload(text, encoding="cp1252").json()
        self.assertEqual(r["rows_created"], 1, r)
        self.assertTrue(Product.objects.filter(organization=self.biz, name="Crème fraîche").exists())

    def test_expiry_before_received_rejected(self):
        r = self.upload("name,quantity,received_date,expiry_date\nMilk,2,2099-01-05,2099-01-01\n").json()
        self.assertEqual(r["rows_failed"], 1)

    def test_transactions_mode_and_validation(self):
        text = ("sku,name,type,quantity,occurred_at\n"
                "MLK,Milk,sale,5,2026-01-01\nMLK,Milk,sale,0,2026-01-02\nMLK,Milk,teleport,1,2026-01-03\n")
        r = self.upload(text, mode="transactions").json()
        self.assertEqual((r["rows_created"], r["rows_failed"]), (1, 2))

    def test_empty_file_rejected_cleanly(self):
        r = self.upload("")
        self.assertEqual(r.status_code, 400)
        self.assertIn("file", r.json())

    def test_header_only_file(self):
        r = self.upload("name,quantity\n")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["rows_total"], 0)

    def test_template_download(self):
        r = self.api(self.u_biz).get("/api/inventory/csv-template/?mode=inventory")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"expiry_date", r.content)


class ScanAndPOSTests(FBTestCase):
    def test_scan_unknown_barcode(self):
        c = self.api(self.u_biz)
        self.assertEqual(c.post("/api/inventory/scan/", {"barcode": "999", "action": "sell"}, format="json").status_code, 400)
        r = c.post("/api/inventory/scan/", {"barcode": "999", "action": "receive", "quantity": 6,
                                            "name": "Brown bread loaf"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["product"]["category_detail"]["slug"], "bakery")
        r = c.post("/api/inventory/scan/", {"barcode": "999", "action": "sell", "quantity": 2}, format="json")
        self.assertEqual(r.json()["product"]["on_hand"], 4)

    def test_barcode_lookup_is_tenant_scoped(self):
        self.product(org=self.biz2, name="Their bread", barcode="777")
        self.assertEqual(self.api(self.u_biz).get("/api/inventory/products/by-barcode/777/").status_code, 404)

    def test_pos_key_auth_and_idempotency(self):
        p = self.product(sku="MLK-1", name="Milk")
        self.stock(qty=10, product=p)
        key = POSIntegration.objects.create(organization=self.biz, name="Till").api_key
        body = {"transactions": [{"sku": "MLK-1", "quantity": 3, "reference": "BILL-1"}]}
        anon = self.api()
        self.assertIn(anon.post("/api/pos/v1/sales/", body, format="json").status_code, (401, 403))
        self.assertIn(anon.post("/api/pos/v1/sales/", body, format="json", HTTP_X_POS_KEY="wrong").status_code, (401, 403))
        r = anon.post("/api/pos/v1/sales/", body, format="json", HTTP_X_POS_KEY=key)
        self.assertEqual(r.json()["results"][0]["status"], "recorded")
        r = anon.post("/api/pos/v1/sales/", body, format="json", HTTP_X_POS_KEY=key)
        self.assertEqual(r.json()["results"][0]["status"], "duplicate_ignored")
        self.assertEqual(sum(b.quantity for b in p.batches.all()), 7)

    def test_disabled_pos_key_rejected(self):
        integ = POSIntegration.objects.create(organization=self.biz, name="Till", is_active=False)
        r = self.api().get("/api/pos/v1/products/", HTTP_X_POS_KEY=integ.api_key)
        self.assertIn(r.status_code, (401, 403))


class ExpiryEngineTests(FBTestCase):
    def test_levels_and_idempotency(self):
        self.stock(qty=2, days=-1, name="Old milk", sku="A")
        self.stock(qty=2, days=0, name="Today milk", sku="B")
        self.stock(qty=2, days=2, name="Soon milk", sku="C")      # dairy warning=3 critical=1
        self.stock(qty=2, days=90, name="Fine rice", slug="grains", sku="D")
        run_expiry_scan(self.biz)
        levels = sorted(ExpiryAlert.objects.filter(organization=self.biz).values_list("level", flat=True))
        self.assertEqual(levels, ["critical", "expired", "warning"])
        again = run_expiry_scan(self.biz)
        self.assertEqual(again["alerts_created"], 0)
        self.assertEqual(self.biz.notifications.filter(kind="expiry").count(), 1)

    def test_org_threshold_override(self):
        ExpiryThreshold.objects.create(organization=self.biz, category=self.cat["grains"], warning_days=40, critical_days=10)
        self.stock(qty=2, days=30, name="Rice", slug="grains")
        run_expiry_scan(self.biz)
        self.assertEqual(ExpiryAlert.objects.get(organization=self.biz).level, "warning")

    def test_alert_acknowledge_and_filter(self):
        self.stock(qty=2, days=0)
        run_expiry_scan(self.biz)
        c = self.api(self.u_biz)
        a = c.get("/api/expiry/alerts/?is_acknowledged=false").json()["results"][0]
        c.post(f"/api/expiry/alerts/{a['id']}/acknowledge/")
        self.assertEqual(c.get("/api/expiry/alerts/?is_acknowledged=false").json()["count"], 0)


class TaxonomyTests(FBTestCase):
    def test_classifier(self):
        c = self.api(self.u_biz)
        for text, slug in [("veg biryani 40 portions", "cooked-meals"), ("banana robusta", "fruits"),
                           ("toor dal 1kg", "grains")]:
            r = c.post("/api/taxonomy/categories/classify/", {"text": text}, format="json").json()
            self.assertEqual(r["category"]["slug"] if r["category"] else None, slug, text)

    def test_every_category_has_storage_and_perishability(self):
        for cat in self.cat.values():
            self.assertIn(cat.perishability, ("high", "medium", "low"))
            self.assertTrue(cat.storage)
