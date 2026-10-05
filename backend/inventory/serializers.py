from rest_framework import serializers

from inventory.models import (BulkUpload, ExpiryAlert, ExpiryThreshold, FoodCategory, InventoryBatch,
                              POSIntegration, Product, StockTransaction)



class OrgScopedPrimaryKey(serializers.PrimaryKeyRelatedField):
    """Only accepts objects that belong to the requesting user's organization (tenant isolation)."""

    def get_queryset(self):
        qs = super().get_queryset()
        req = self.context.get("request")
        org_id = getattr(getattr(req, "user", None), "organization_id", None)
        return qs.filter(organization_id=org_id) if org_id else qs

class FoodCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodCategory
        fields = ["id", "slug", "name", "parent", "perishability", "storage", "storage_temp_c",
                  "default_shelf_life_days", "warning_days", "critical_days", "co2e_per_kg", "keywords",
                  "handling_notes", "color"]


class CategoryMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodCategory
        fields = ["id", "slug", "name", "perishability", "storage", "color"]


class ProductSerializer(serializers.ModelSerializer):
    category_detail = CategoryMiniSerializer(source="category", read_only=True)
    category = serializers.PrimaryKeyRelatedField(queryset=FoodCategory.objects.all(), required=False, allow_null=True)
    on_hand = serializers.FloatField(read_only=True, required=False)
    auto_classified = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Product
        fields = ["id", "name", "sku", "barcode", "category", "category_detail", "unit", "unit_weight_kg",
                  "unit_cost", "shelf_life_days", "reorder_point", "storage_space_per_unit_kg",
                  "fr_product_id", "fr_first_category_id", "is_active", "on_hand", "auto_classified", "created_at"]
        read_only_fields = ["created_at"]
        extra_kwargs = {"sku": {"required": False}}


class BatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_unit = serializers.CharField(source="product.unit", read_only=True)
    category = CategoryMiniSerializer(source="product.category", read_only=True)
    days_to_expiry = serializers.IntegerField(read_only=True)
    weight_kg = serializers.FloatField(read_only=True)
    value = serializers.FloatField(read_only=True)
    product = OrgScopedPrimaryKey(queryset=Product.objects.all())

    class Meta:
        model = InventoryBatch
        fields = ["id", "product", "product_name", "product_unit", "category", "batch_code", "quantity",
                  "initial_quantity", "received_date", "expiry_date", "days_to_expiry", "storage_location",
                  "status", "weight_kg", "value", "risk_score", "risk_level", "risk_factors",
                  "predicted_demand", "expected_waste_qty", "recommended_action", "risk_model",
                  "risk_updated_at", "created_at"]
        read_only_fields = ["initial_quantity", "status", "risk_score", "risk_level", "risk_factors",
                            "predicted_demand", "expected_waste_qty", "recommended_action", "risk_model",
                            "risk_updated_at", "created_at"]
        extra_kwargs = {"expiry_date": {"required": False}}

    def validate_product(self, p):
        req = self.context["request"]
        if not req.user.is_superuser and p.organization_id != req.user.organization_id:
            raise serializers.ValidationError("Product belongs to another organization.")
        return p


class TransactionSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product = OrgScopedPrimaryKey(queryset=Product.objects.all())

    class Meta:
        model = StockTransaction
        fields = ["id", "product", "product_name", "batch", "txn_type", "quantity", "unit_price", "occurred_at",
                  "source", "reference", "note", "discount", "holiday_flag", "activity_flag", "stockout_hours"]
        read_only_fields = ["batch", "source"]
        extra_kwargs = {"occurred_at": {"required": False}}


class ExpiryThresholdSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default="All categories")

    class Meta:
        model = ExpiryThreshold
        fields = ["id", "category", "category_name", "warning_days", "critical_days"]

    def validate(self, attrs):
        if attrs.get("critical_days", 0) > attrs.get("warning_days", 10**6):
            raise serializers.ValidationError("critical_days must be <= warning_days")
        return attrs


class ExpiryAlertSerializer(serializers.ModelSerializer):
    batch = BatchSerializer(read_only=True)

    class Meta:
        model = ExpiryAlert
        fields = ["id", "level", "days_left", "message", "is_acknowledged", "created_at", "batch"]
        read_only_fields = ["level", "days_left", "message", "created_at", "batch"]


class POSIntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = POSIntegration
        fields = ["id", "name", "provider", "api_key", "is_active", "last_sync_at", "events_received", "created_at"]
        read_only_fields = ["api_key", "last_sync_at", "events_received", "created_at"]


class BulkUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkUpload
        fields = ["id", "file_name", "mode", "rows_total", "rows_created", "rows_failed", "errors", "created_at"]


class CSVUploadRequest(serializers.Serializer):
    file = serializers.FileField()
    mode = serializers.ChoiceField(choices=["inventory", "transactions"], default="inventory")


class ScanRequest(serializers.Serializer):
    barcode = serializers.CharField(max_length=64)
    action = serializers.ChoiceField(choices=["receive", "sell", "waste", "remove"])
    quantity = serializers.FloatField(min_value=0.001, default=1)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    name = serializers.CharField(required=False, allow_blank=True, help_text="Required to create a new product")
    category = serializers.CharField(required=False, allow_blank=True)


class ClassifyRequest(serializers.Serializer):
    text = serializers.CharField()


class ClassifyResponse(serializers.Serializer):
    category = FoodCategorySerializer(allow_null=True)
    confidence = serializers.FloatField()
    matched_keywords = serializers.ListField(child=serializers.CharField())


class AdjustRequest(serializers.Serializer):
    quantity = serializers.FloatField(min_value=0.001)
    reason = serializers.ChoiceField(choices=["sale", "waste", "adjustment", "donation"], default="waste")
    note = serializers.CharField(required=False, allow_blank=True)


# ---- POS payloads
class POSSaleLine(serializers.Serializer):
    sku = serializers.CharField(required=False, allow_blank=True)
    barcode = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.FloatField(min_value=0.001)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    occurred_at = serializers.DateTimeField(required=False)
    reference = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get("sku") and not attrs.get("barcode"):
            raise serializers.ValidationError("sku or barcode is required")
        return attrs


class POSSalesRequest(serializers.Serializer):
    transactions = POSSaleLine(many=True)


class POSReceiptLine(serializers.Serializer):
    sku = serializers.CharField(required=False, allow_blank=True)
    barcode = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.FloatField(min_value=0.001)
    unit_cost = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    expiry_date = serializers.DateField(required=False)
    reference = serializers.CharField(required=False, allow_blank=True)


class POSReceiptsRequest(serializers.Serializer):
    items = POSReceiptLine(many=True)
