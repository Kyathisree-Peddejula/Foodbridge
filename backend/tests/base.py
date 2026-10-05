"""Shared fixtures for the FoodBridge test-suite."""
import io
import os
import sys
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organization, User
from inventory.models import FoodCategory, Product
from inventory.services import receive_stock

TODAY = timezone.localdate


def later(hours=2, days=0):
    return timezone.now() + timedelta(hours=hours, days=days)


def iso(dt):
    return dt.isoformat()


# ML service is unreachable by default so tests are deterministic (heuristic fallback)
@override_settings(ML_SERVICE_URL="http://127.0.0.1:9", ML_SERVICE_TIMEOUT=0.3,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FBTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = {c.slug: c for c in FoodCategory.objects.all()}
        cls.biz = cls.make_org("Test Bistro", "business", 12.9716, 77.5946, kind="restaurant")
        cls.biz2 = cls.make_org("Other Mart", "business", 12.9800, 77.6000, kind="supermarket")
        cls.ngo = cls.make_org("Near NGO", "ngo", 12.9750, 77.5950, kind="ngo", daily_capacity_kg=300,
                               beneficiaries=120)
        cls.ngo_far = cls.make_org("Far NGO", "ngo", 13.3000, 77.9000, kind="food_bank", daily_capacity_kg=300)
        cls.u_biz = cls.make_user("owner@bistro.test", cls.biz, "business")
        cls.u_biz2 = cls.make_user("owner@mart.test", cls.biz2, "business")
        cls.u_ngo = cls.make_user("lead@ngo.test", cls.ngo, "ngo")
        cls.u_ngo_far = cls.make_user("lead@far.test", cls.ngo_far, "ngo")
        cls.admin = User.objects.create_superuser(username="admin@fb.test", email="admin@fb.test",
                                                  password="x", role="admin")

    @staticmethod
    def make_org(name, org_type, lat, lng, **kw):
        return Organization.objects.create(name=name, org_type=org_type, latitude=lat, longitude=lng,
                                           address=f"{name} street", city="Bengaluru", **kw)

    @staticmethod
    def make_user(email, org, role):
        return User.objects.create_user(username=email, email=email, password="Pass@12345", organization=org,
                                        role=role)

    def api(self, user=None):
        c = APIClient()
        if user:
            c.force_authenticate(user)
        return c

    def product(self, org=None, name="Paneer", slug="dairy", unit="kg", **kw):
        return Product.objects.create(organization=org or self.biz, name=name, sku=kw.pop("sku", name[:6].upper()),
                                      unit=unit, category=self.cat[slug], unit_weight_kg=kw.pop("unit_weight_kg", 1),
                                      **kw)

    def stock(self, qty=20, days=2, **kw):
        p = kw.pop("product", None) or self.product(**kw)
        return receive_stock(p, qty, expiry_date=TODAY() + timedelta(days=days))

    @staticmethod
    def csv(text, name="upload.csv", encoding="utf-8"):
        f = io.BytesIO(text.encode(encoding))
        f.name = name
        return f


# ---------------------------------------------------------------- in-process ML service
ML_DIR = Path(__file__).resolve().parents[2] / "ml_service"


@contextmanager
def live_ml_service():
    """Route Django's ML client to the real FastAPI app in-process (no network needed)."""
    os.environ.setdefault("ENABLE_SCHEDULER", "false")
    if str(ML_DIR) not in sys.path:
        sys.path.insert(0, str(ML_DIR))
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as ml:
        def _resp(r):
            m = mock.Mock(status_code=r.status_code)
            m.json.return_value = r.json()
            m.raise_for_status = lambda: None if r.status_code < 400 else (_ for _ in ()).throw(
                __import__("requests").HTTPError(r.text))
            return m

        def post(url, json=None, **_):
            return _resp(ml.post("/" + url.split("/", 3)[3], json=json))

        def get(url, params=None, **_):
            return _resp(ml.get("/" + url.split("/", 3)[3], params=params))

        with mock.patch("predictions.client.requests.post", side_effect=post), \
                mock.patch("predictions.client.requests.get", side_effect=get), \
                override_settings(ML_SERVICE_URL="http://ml.test:8001"):
            yield ml
