import secrets
from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone


class FoodCategory(models.Model):
    """Food taxonomy node with perishability risk and storage requirements."""

    class Perishability(models.TextChoices):
        HIGH = "high", "High (hours to days)"
        MEDIUM = "medium", "Medium (days to weeks)"
        LOW = "low", "Low (weeks to months)"

    class Storage(models.TextChoices):
        FROZEN = "frozen", "Frozen (-18 °C)"
        CHILLED = "chilled", "Chilled (0-5 °C)"
        AMBIENT = "ambient", "Ambient / dry"
        HOT_HOLD = "hot_hold", "Hot holding (>63 °C)"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    perishability = models.CharField(max_length=8, choices=Perishability.choices)
    storage = models.CharField(max_length=10, choices=Storage.choices)
    storage_temp_c = models.CharField(max_length=20, blank=True)
    default_shelf_life_days = models.PositiveIntegerField()
    warning_days = models.PositiveIntegerField(help_text="Alert when days-to-expiry <= this")
    critical_days = models.PositiveIntegerField(help_text="Critical alert when days-to-expiry <= this")
    co2e_per_kg = models.FloatField(default=2.5, help_text="kg CO2e avoided per kg rescued")
    keywords = models.TextField(blank=True, help_text="Comma-separated words used by the auto-classifier")
    handling_notes = models.CharField(max_length=255, blank=True)
    color = models.CharField(max_length=9, default="#1FA463")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "food categories"

    def keyword_list(self):
        return [k.strip().lower() for k in self.keywords.split(",") if k.strip()]

    def __str__(self):
        return self.name


class Product(models.Model):
    class Unit(models.TextChoices):
        KG = "kg", "Kilogram"
        G = "g", "Gram"
        L = "l", "Litre"
        ML = "ml", "Millilitre"
        PCS = "pcs", "Pieces"
        PACK = "pack", "Pack"
        PORTION = "portion", "Portion / meal"

    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=160)
    sku = models.CharField(max_length=64)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    category = models.ForeignKey(FoodCategory, null=True, on_delete=models.SET_NULL, related_name="products")
    unit = models.CharField(max_length=8, choices=Unit.choices, default=Unit.KG)
    unit_weight_kg = models.FloatField(default=1.0, help_text="kg per unit, used for impact metrics")
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shelf_life_days = models.PositiveIntegerField(null=True, blank=True, help_text="Overrides category default")
    reorder_point = models.FloatField(default=0)
    storage_space_per_unit_kg = models.FloatField(default=1.0)
    # FreshRetailNet-50K linkage (lets the ML service use the series-level model)
    fr_product_id = models.IntegerField(null=True, blank=True, db_index=True)
    fr_first_category_id = models.IntegerField(null=True, blank=True)
    fr_second_category_id = models.IntegerField(null=True, blank=True)
    fr_third_category_id = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("organization", "sku")]
        constraints = [models.UniqueConstraint(fields=["organization", "barcode"], condition=~models.Q(barcode=""),
                                               name="uniq_org_barcode")]

    @property
    def effective_shelf_life(self):
        return self.shelf_life_days or (self.category.default_shelf_life_days if self.category else 7)

    def __str__(self):
        return f"{self.name} ({self.sku})"


class InventoryBatch(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        EXPIRING = "expiring", "Expiring soon"
        EXPIRED = "expired", "Expired"
        LISTED = "listed", "Listed for donation"
        DEPLETED = "depleted", "Depleted"

    class RiskLevel(models.TextChoices):
        UNKNOWN = "unknown", "Not scored"
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="batches")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="batches")
    batch_code = models.CharField(max_length=64, blank=True)
    quantity = models.FloatField()
    initial_quantity = models.FloatField(default=0)
    received_date = models.DateField(default=date.today)
    expiry_date = models.DateField()
    storage_location = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    # AI waste-risk output (written by the prediction service)
    risk_score = models.FloatField(null=True, blank=True)
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices, default=RiskLevel.UNKNOWN, db_index=True)
    risk_factors = models.JSONField(default=dict, blank=True)
    predicted_demand = models.FloatField(null=True, blank=True, help_text="Units forecast to sell before expiry")
    expected_waste_qty = models.FloatField(null=True, blank=True)
    recommended_action = models.CharField(max_length=200, blank=True)
    risk_model = models.CharField(max_length=40, blank=True)
    risk_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["expiry_date", "id"]
        indexes = [models.Index(fields=["organization", "status", "expiry_date"])]

    def save(self, *args, **kwargs):
        if not self.initial_quantity:
            self.initial_quantity = self.quantity
        if not self.batch_code:
            self.batch_code = f"B{secrets.token_hex(3).upper()}"
        super().save(*args, **kwargs)

    @property
    def days_to_expiry(self):
        return (self.expiry_date - timezone.localdate()).days

    @property
    def weight_kg(self):
        return round(self.quantity * (self.product.unit_weight_kg or 1.0), 3)

    @property
    def value(self):
        return round(float(self.product.unit_cost) * self.quantity, 2)

    def __str__(self):
        return f"{self.product.name} · {self.batch_code}"


class StockTransaction(models.Model):
    class Type(models.TextChoices):
        PURCHASE = "purchase", "Purchase / receipt"
        SALE = "sale", "Sale"
        WASTE = "waste", "Waste / discard"
        DONATION = "donation", "Donation"
        ADJUSTMENT = "adjustment", "Stock adjustment"
        RETURN = "return", "Return"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual entry"
        CSV = "csv", "CSV upload"
        POS = "pos", "POS integration"
        SCAN = "scan", "Barcode scan"
        IMPORT = "import", "Dataset import"
        SYSTEM = "system", "System"

    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="transactions")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="transactions")
    batch = models.ForeignKey(InventoryBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    txn_type = models.CharField(max_length=12, choices=Type.choices, db_index=True)
    quantity = models.FloatField(help_text="Always positive; direction comes from txn_type")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    occurred_at = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.MANUAL)
    reference = models.CharField(max_length=80, blank=True, db_index=True)
    note = models.CharField(max_length=255, blank=True)
    # context features used by the forecaster (mirrors FreshRetailNet columns)
    discount = models.FloatField(null=True, blank=True)
    holiday_flag = models.BooleanField(default=False)
    activity_flag = models.BooleanField(default=False)
    stockout_hours = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["organization", "product", "txn_type", "occurred_at"])]


class ExpiryThreshold(models.Model):
    """Org-level override of when alerts fire. category=None is the organization default."""
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="expiry_thresholds")
    category = models.ForeignKey(FoodCategory, null=True, blank=True, on_delete=models.CASCADE)
    warning_days = models.PositiveIntegerField()
    critical_days = models.PositiveIntegerField()

    class Meta:
        unique_together = [("organization", "category")]


class ExpiryAlert(models.Model):
    class Level(models.TextChoices):
        WARNING = "warning", "Approaching expiry"
        CRITICAL = "critical", "Critical"
        EXPIRED = "expired", "Expired"

    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="expiry_alerts")
    batch = models.ForeignKey(InventoryBatch, on_delete=models.CASCADE, related_name="alerts")
    level = models.CharField(max_length=10, choices=Level.choices)
    days_left = models.IntegerField()
    message = models.CharField(max_length=255)
    is_acknowledged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("batch", "level")]


def _new_key():
    return "pos_" + secrets.token_urlsafe(24)


class POSIntegration(models.Model):
    class Provider(models.TextChoices):
        GENERIC = "generic", "Generic REST"
        SQUARE = "square", "Square"
        LIGHTSPEED = "lightspeed", "Lightspeed"
        PETPOOJA = "petpooja", "Petpooja"
        TOAST = "toast", "Toast"

    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="pos_integrations")
    name = models.CharField(max_length=80)
    provider = models.CharField(max_length=16, choices=Provider.choices, default=Provider.GENERIC)
    api_key = models.CharField(max_length=64, unique=True, default=_new_key)
    is_active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    events_received = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def rotate(self):
        self.api_key = _new_key()
        self.save(update_fields=["api_key"])


class BulkUpload(models.Model):
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="uploads")
    file_name = models.CharField(max_length=200)
    mode = models.CharField(max_length=16, default="inventory")
    rows_total = models.PositiveIntegerField(default=0)
    rows_created = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
