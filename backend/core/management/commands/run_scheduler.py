"""Background jobs: expiry scan, pickup reminders, listing expiry, and scheduled risk scoring."""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from django.conf import settings
from django.core.management.base import BaseCommand

log = logging.getLogger(__name__)


def expiry_job():
    from inventory.services import run_expiry_scan
    log.info("expiry scan: %s", run_expiry_scan())


def pickups_job():
    from marketplace.services import expire_listings, send_reminders
    log.info("reminders sent: %s, listings expired: %s", send_reminders(), expire_listings())


def risk_job():
    from accounts.models import Organization
    from predictions.models import PredictionRun
    from predictions.services import refresh_risk
    for org in Organization.objects.filter(org_type="business"):
        run, res = refresh_risk(org, source=PredictionRun.Source.SCHEDULED)
        log.info("risk %s: %s via %s", org.name, res, run.engine)


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, p):
        p.add_argument("--risk-every-hours", type=int, default=6)
        p.add_argument("--once", action="store_true", help="run every job once and exit")

    def handle(self, *args, **o):
        if o["once"]:
            expiry_job(); pickups_job(); risk_job()  # noqa: E702
            return
        s = BlockingScheduler(timezone=settings.TIME_ZONE)
        s.add_job(expiry_job, "interval", minutes=settings.EXPIRY_SCAN_INTERVAL_MIN, next_run_time=None)
        s.add_job(pickups_job, "interval", minutes=15)
        s.add_job(risk_job, "interval", hours=o["risk_every_hours"])
        s.add_job(expiry_job, "cron", hour=6, minute=0, id="morning-expiry")
        self.stdout.write(self.style.SUCCESS("Scheduler running. Ctrl+C to stop."))
        expiry_job()
        s.start()
