from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class DietaryTag(models.TextChoices):
    VEG = "veg", "Vegetarian"
    NON_VEG = "non_veg", "Non-vegetarian"
    VEGAN = "vegan", "Vegan"
    JAIN = "jain", "Jain"
    HALAL = "halal", "Halal"
    CONTAINS_NUTS = "contains_nuts", "Contains nuts"
    CONTAINS_DAIRY = "contains_dairy", "Contains dairy"
    GLUTEN_FREE = "gluten_free", "Gluten free"


class SurplusListing(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED = "reserved", "Fully reserved"
        COMPLETED = "completed", "Picked up"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    donor = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="listings")
    batch = models.ForeignKey("inventory.InventoryBatch", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="listings")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    category = models.ForeignKey("inventory.FoodCategory", null=True, on_delete=models.SET_NULL)
    quantity_kg = models.FloatField()
    quantity_units = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=12, default="kg")
    expiry_date = models.DateField()
    pickup_address = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dietary_tags = models.JSONField(default=list, blank=True)
    requires_refrigeration = models.BooleanField(default=False)
    handling_notes = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    auto_suggested = models.BooleanField(default=False, help_text="Created from an AI waste-risk suggestion")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    ACTIVE_PICKUP_STATES = ("requested", "confirmed", "in_transit", "completed")

    @property
    def reserved_kg(self):
        if hasattr(self, "reserved_kg_annot"):          # set by with_pickup_stats() - avoids N+1 in lists
            return self.reserved_kg_annot or 0.0
        return self.pickups.filter(status__in=self.ACTIVE_PICKUP_STATES).aggregate(s=Sum("quantity_kg"))["s"] or 0.0

    @property
    def remaining_kg(self):
        return max(0.0, round(self.quantity_kg - self.reserved_kg, 3))

    @property
    def estimated_meals(self):
        return int(self.quantity_kg / settings.IMPACT["KG_PER_MEAL"])

    @property
    def days_to_expiry(self):
        return (self.expiry_date - timezone.localdate()).days

    def refresh_status(self):
        if self.status in (self.Status.CANCELLED,):
            return
        pickups = self.pickups.all()
        if self.days_to_expiry < 0 and not pickups.filter(status__in=["confirmed", "in_transit"]).exists():
            new = self.Status.EXPIRED if not pickups.filter(status="completed").exists() else self.Status.COMPLETED
        elif self.remaining_kg <= 0.001:
            open_ = pickups.filter(status__in=["requested", "confirmed", "in_transit"]).exists()
            new = self.Status.RESERVED if open_ else self.Status.COMPLETED
        else:
            new = self.Status.AVAILABLE
        if new != self.status:
            self.status = new
            self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return self.title


class AvailabilityWindow(models.Model):
    listing = models.ForeignKey(SurplusListing, on_delete=models.CASCADE, related_name="windows")
    start = models.DateTimeField()
    end = models.DateTimeField()

    class Meta:
        ordering = ["start"]


class NGORequirement(models.Model):
    ngo = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="requirements")
    title = models.CharField(max_length=160)
    categories = models.ManyToManyField("inventory.FoodCategory", blank=True)
    min_quantity_kg = models.FloatField(default=0)
    max_quantity_kg = models.FloatField(default=500)
    max_distance_km = models.FloatField(default=15)
    dietary_restrictions = models.JSONField(default=list, blank=True,
                                            help_text="Tags the NGO can accept only, e.g. ['veg']")
    has_refrigeration = models.BooleanField(default=False)
    pickup_days = models.JSONField(default=list, blank=True, help_text="0=Mon … 6=Sun; empty = any day")
    pickup_from_hour = models.PositiveSmallIntegerField(default=8)
    pickup_to_hour = models.PositiveSmallIntegerField(default=21)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ngo.name}: {self.title}"


class Match(models.Model):
    class Status(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        REQUESTED = "requested", "Pickup requested"
        DECLINED = "declined", "Declined"

    listing = models.ForeignKey(SurplusListing, on_delete=models.CASCADE, related_name="matches")
    ngo = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="matches")
    requirement = models.ForeignKey(NGORequirement, null=True, blank=True, on_delete=models.SET_NULL)
    score = models.FloatField()
    distance_km = models.FloatField(null=True, blank=True)
    breakdown = models.JSONField(default=dict)
    reasons = models.JSONField(default=list)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUGGESTED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score"]
        unique_together = [("listing", "ngo")]


class Pickup(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Awaiting confirmation"
        CONFIRMED = "confirmed", "Scheduled"
        IN_TRANSIT = "in_transit", "In transit"
        COMPLETED = "completed", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No-show"

    listing = models.ForeignKey(SurplusListing, on_delete=models.CASCADE, related_name="pickups")
    ngo = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="pickups")
    match = models.ForeignKey(Match, null=True, blank=True, on_delete=models.SET_NULL)
    quantity_kg = models.FloatField()
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    initiated_by = models.CharField(max_length=8, default="ngo", help_text="ngo = claim, donor = offer")
    donor_confirmed_at = models.DateTimeField(null=True, blank=True)
    ngo_confirmed_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    quantity_received_kg = models.FloatField(null=True, blank=True)
    meals_served = models.PositiveIntegerField(null=True, blank=True)
    beneficiaries_served = models.PositiveIntegerField(null=True, blank=True)
    driver_name = models.CharField(max_length=80, blank=True)
    driver_phone = models.CharField(max_length=32, blank=True)
    vehicle = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    reminder_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_start"]
