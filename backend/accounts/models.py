from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify


class Organization(models.Model):
    """A tenant. Food businesses donate; NGOs / community kitchens / food banks receive."""

    class OrgType(models.TextChoices):
        BUSINESS = "business", "Food business"
        NGO = "ngo", "Recipient organization"

    class BusinessKind(models.TextChoices):
        RESTAURANT = "restaurant", "Restaurant"
        SUPERMARKET = "supermarket", "Supermarket"
        BAKERY = "bakery", "Bakery"
        CANTEEN = "canteen", "Canteen / cafeteria"
        HOTEL = "hotel", "Hotel / caterer"
        HOUSEHOLD = "household", "Household"
        NGO = "ngo", "NGO"
        COMMUNITY_KITCHEN = "community_kitchen", "Community kitchen"
        FOOD_BANK = "food_bank", "Food bank"
        SHELTER = "shelter", "Shelter"

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    org_type = models.CharField(max_length=16, choices=OrgType.choices)
    kind = models.CharField(max_length=24, choices=BusinessKind.choices, blank=True)
    contact_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=80, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    # business
    storage_capacity_kg = models.FloatField(default=1000, help_text="Total storage capacity used by reorder advice")
    reorder_lead_time_days = models.PositiveSmallIntegerField(default=2)
    # ngo
    daily_capacity_kg = models.FloatField(default=200, help_text="How much food the NGO can take per day")
    beneficiaries = models.PositiveIntegerField(default=0, help_text="People served regularly")
    can_pickup = models.BooleanField(default=True, help_text="NGO has its own vehicle")
    reliability_score = models.FloatField(default=0.8, help_text="0-1, learned from pickup history")
    # dataset linkage (FreshRetailNet-50K)
    fr_store_id = models.IntegerField(null=True, blank=True, db_index=True)
    fr_city_id = models.IntegerField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:160] or "org"
            slug, i = base, 1
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        BUSINESS = "business", "Business staff"
        NGO = "ngo", "NGO staff"
        ADMIN = "admin", "Platform admin"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.BUSINESS)
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="members")
    phone = models.CharField(max_length=32, blank=True)

    def __str__(self):
        return self.email or self.username
