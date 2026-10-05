from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        EXPIRY = "expiry", "Expiry alert"
        RISK = "risk", "Waste risk"
        MATCH = "match", "Donation match"
        PICKUP = "pickup", "Pickup update"
        LISTING = "listing", "Listing update"
        SYSTEM = "system", "System"

    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="notifications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=200, blank=True, help_text="In-app route, e.g. /pickups/12")
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "is_read", "-created_at"])]

    def __str__(self):
        return self.title
