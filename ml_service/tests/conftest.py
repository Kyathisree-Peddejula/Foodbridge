import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("ENABLE_SCHEDULER", "false")          # no background pulls from Django during tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:                              # runs lifespan → loads trained artifacts
        yield c


def item(**kw):
    base = dict(batch_id=1, product_id=1, product_name="Milk", unit="l", category_slug="dairy",
                perishability="high", shelf_life_days=5, quantity=20, days_to_expiry=2,
                recent_daily_sales=[4.0] * 28)
    base.update(kw)
    return base
