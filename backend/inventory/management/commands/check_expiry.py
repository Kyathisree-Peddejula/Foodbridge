from django.core.management.base import BaseCommand

from inventory.services import run_expiry_scan


class Command(BaseCommand):
    help = "Run the expiry tracking engine for all tenants (statuses + alerts + notifications)."

    def handle(self, *args, **opts):
        self.stdout.write(self.style.SUCCESS(str(run_expiry_scan())))
