"""
Locust version of the load test, with a live web UI and charts:

    pip install locust
    locust -f tests/load/locustfile.py --host http://localhost:8000
    # open http://localhost:8089, e.g. 200 users, spawn rate 20
Headless:  locust -f tests/load/locustfile.py --host http://localhost:8000 -u 100 -r 10 -t 2m --headless --csv tests/load/locust
"""
import random

from locust import HttpUser, between, task


class _Base(HttpUser):
    abstract = True
    wait_time = between(1, 4)          # realistic think time between clicks
    accounts = []

    def on_start(self):
        email, pw = random.choice(self.accounts)
        r = self.client.post("/api/auth/login/", json={"email": email, "password": pw}, name="login")
        self.client.headers["Authorization"] = f"Bearer {r.json()['access']}"


class BusinessUser(_Base):
    weight = 6
    accounts = [("hotel@foodbridge.dev", "Demo@12345"), ("bakery@foodbridge.dev", "Demo@12345"),
                ("store4@foodbridge.dev", "Demo@12345")]

    @task(5)
    def dashboard(self):
        self.client.get("/api/analytics/business/")

    @task(4)
    def inventory(self):
        self.client.get("/api/inventory/batches/?in_stock=true&page_size=50", name="/api/inventory/batches/")

    @task(2)
    def listings(self):
        self.client.get("/api/marketplace/listings/?page_size=50", name="/api/marketplace/listings/")
        self.client.get("/api/marketplace/listings/suggestions/")

    @task(2)
    def predictions(self):
        self.client.get("/api/predictions/risk/summary/")

    @task(2)
    def poll_bell(self):
        self.client.get("/api/notifications/unread-count/")

    @task(1)
    def scan(self):
        self.client.post("/api/inventory/scan/", json={"barcode": f"LOAD-{random.randint(1, 20)}", "action": "receive",
                                                       "quantity": 1, "name": "Load test bread"})


class NgoUser(_Base):
    weight = 3
    accounts = [("hope@foodbridge.dev", "Demo@12345"), ("annapoorna@foodbridge.dev", "Demo@12345")]

    @task(6)
    def live_feed(self):
        self.client.get("/api/marketplace/listings/feed/")

    @task(3)
    def dashboard(self):
        self.client.get("/api/analytics/ngo/")

    @task(2)
    def pickups(self):
        self.client.get("/api/pickups/calendar/")


class AdminUser(_Base):
    weight = 1
    accounts = [("admin@foodbridge.dev", "Admin@12345")]

    @task
    def overview(self):
        self.client.get("/api/analytics/admin/")
        self.client.get("/api/analytics/impact/?scope=platform")
