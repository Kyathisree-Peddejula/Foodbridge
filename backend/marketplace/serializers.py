from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.serializers import OrganizationPublicSerializer
from inventory.models import FoodCategory, InventoryBatch
from inventory.serializers import CategoryMiniSerializer
from marketplace.models import AvailabilityWindow, DietaryTag, Match, NGORequirement, Pickup, SurplusListing


class WindowSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilityWindow
        fields = ["id", "start", "end"]

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError("Window end must be after start")
        return attrs


class MatchSerializer(serializers.ModelSerializer):
    ngo = OrganizationPublicSerializer(read_only=True)

    class Meta:
        model = Match
        fields = ["id", "ngo", "requirement", "score", "distance_km", "breakdown", "reasons", "status", "created_at"]


class ListingSerializer(serializers.ModelSerializer):
    windows = WindowSerializer(many=True, required=False)
    donor = OrganizationPublicSerializer(read_only=True)
    category = serializers.PrimaryKeyRelatedField(queryset=FoodCategory.objects.all(), required=False, allow_null=True)
    category_detail = CategoryMiniSerializer(source="category", read_only=True)
    dietary_tags = serializers.ListField(child=serializers.ChoiceField(choices=DietaryTag.choices), required=False)
    remaining_kg = serializers.FloatField(read_only=True)
    estimated_meals = serializers.IntegerField(read_only=True)
    days_to_expiry = serializers.IntegerField(read_only=True)
    match_score = serializers.SerializerMethodField()
    match_reasons = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()
    pickups_count = serializers.SerializerMethodField()

    class Meta:
        model = SurplusListing
        fields = ["id", "donor", "batch", "title", "description", "category", "category_detail", "quantity_kg",
                  "quantity_units", "unit", "expiry_date", "days_to_expiry", "pickup_address", "latitude",
                  "longitude", "dietary_tags", "requires_refrigeration", "handling_notes", "status",
                  "auto_suggested", "windows", "remaining_kg", "estimated_meals", "match_score", "match_reasons",
                  "distance_km", "pickups_count", "created_at", "updated_at"]
        read_only_fields = ["status", "auto_suggested", "created_at", "updated_at"]
        extra_kwargs = {"pickup_address": {"required": False}, "batch": {"read_only": True}}

    def _match(self, obj):
        org = getattr(self.context.get("request").user, "organization", None) if self.context.get("request") else None
        if not org or org.org_type != "ngo":
            return None
        cache = self.context.setdefault("_matches", {})
        if obj.id not in cache:
            cache[obj.id] = next((m for m in obj.matches.all() if m.ngo_id == org.id), None)
        return cache[obj.id]

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_match_score(self, obj):
        m = self._match(obj)
        return m.score if m else None

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_match_reasons(self, obj):
        m = self._match(obj)
        return m.reasons if m else []

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_distance_km(self, obj):
        m = self._match(obj)
        return m.distance_km if m else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_pickups_count(self, obj):
        if hasattr(obj, "pickups_count_annot"):
            return obj.pickups_count_annot
        return obj.pickups.exclude(status__in=["cancelled", "no_show"]).count()

    def validate_quantity_kg(self, v):
        if v <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return v

    def validate_expiry_date(self, v):
        from django.utils import timezone
        if self.instance is None and v < timezone.localdate():
            raise serializers.ValidationError("Expired food cannot be listed for donation")
        return v

    def validate(self, attrs):
        from django.utils import timezone
        expiry = attrs.get("expiry_date") or (self.instance.expiry_date if self.instance else None)
        for w in attrs.get("windows") or []:
            if expiry and timezone.localtime(w["start"]).date() > expiry:
                raise serializers.ValidationError(
                    {"windows": f"Pickup windows must start on or before the best-before date ({expiry:%d %b})"})
        return attrs

    def validate_windows(self, windows):
        from django.utils import timezone
        if any(w["end"] < timezone.now() for w in windows):
            raise serializers.ValidationError("Availability windows must end in the future")
        return windows

    def update(self, instance, data):
        windows = data.pop("windows", None)
        instance = super().update(instance, data)
        if windows is not None:
            instance.windows.all().delete()
            for w in windows:
                AvailabilityWindow.objects.create(listing=instance, **w)
        return instance


class FromBatchRequest(serializers.Serializer):
    batch = serializers.PrimaryKeyRelatedField(queryset=InventoryBatch.objects.all())
    quantity = serializers.FloatField(required=False, min_value=0.001, help_text="Units; default = expected waste")
    title = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    dietary_tags = serializers.ListField(child=serializers.ChoiceField(choices=DietaryTag.choices), required=False)
    windows = WindowSerializer(many=True, required=False)


class RequirementSerializer(serializers.ModelSerializer):
    categories = serializers.PrimaryKeyRelatedField(queryset=FoodCategory.objects.all(), many=True, required=False)
    category_names = serializers.SerializerMethodField()

    class Meta:
        model = NGORequirement
        exclude = ["ngo"]

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_category_names(self, obj):
        return [c.name for c in obj.categories.all()]

    def validate(self, attrs):
        if attrs.get("min_quantity_kg", 0) > attrs.get("max_quantity_kg", 10**9):
            raise serializers.ValidationError("min_quantity_kg must be <= max_quantity_kg")
        return attrs


class ListingMiniSerializer(serializers.ModelSerializer):
    donor = OrganizationPublicSerializer(read_only=True)
    category_detail = CategoryMiniSerializer(source="category", read_only=True)

    class Meta:
        model = SurplusListing
        fields = ["id", "title", "donor", "category_detail", "quantity_kg", "unit", "expiry_date", "pickup_address",
                  "latitude", "longitude", "status", "requires_refrigeration", "dietary_tags"]


class PickupSerializer(serializers.ModelSerializer):
    listing = ListingMiniSerializer(read_only=True)
    ngo = OrganizationPublicSerializer(read_only=True)
    my_side = serializers.SerializerMethodField()
    awaiting = serializers.SerializerMethodField()

    class Meta:
        model = Pickup
        fields = "__all__"

    @extend_schema_field(OpenApiTypes.STR)
    def get_my_side(self, obj):
        req = self.context.get("request")
        org_id = getattr(req.user, "organization_id", None) if req else None
        return "donor" if obj.listing.donor_id == org_id else "ngo" if obj.ngo_id == org_id else "admin"

    @extend_schema_field(OpenApiTypes.STR)
    def get_awaiting(self, obj):
        if obj.status != "requested":
            return None
        return "donor" if not obj.donor_confirmed_at else "ngo" if not obj.ngo_confirmed_at else None


class ClaimRequest(serializers.Serializer):
    quantity_kg = serializers.FloatField(min_value=0.001)
    window = serializers.PrimaryKeyRelatedField(queryset=AvailabilityWindow.objects.all(), required=False)
    scheduled_start = serializers.DateTimeField(required=False)
    scheduled_end = serializers.DateTimeField(required=False)
    driver_name = serializers.CharField(required=False, allow_blank=True)
    driver_phone = serializers.CharField(required=False, allow_blank=True)
    vehicle = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get("window") and not (attrs.get("scheduled_start") and attrs.get("scheduled_end")):
            raise serializers.ValidationError("Choose an availability window or give scheduled_start and scheduled_end")
        return attrs


class OfferRequest(ClaimRequest):
    ngo = serializers.IntegerField()


class RescheduleRequest(serializers.Serializer):
    scheduled_start = serializers.DateTimeField()
    scheduled_end = serializers.DateTimeField()


class CollectRequest(serializers.Serializer):
    driver_name = serializers.CharField(required=False, allow_blank=True)
    driver_phone = serializers.CharField(required=False, allow_blank=True)
    vehicle = serializers.CharField(required=False, allow_blank=True)


class CompleteRequest(serializers.Serializer):
    quantity_received_kg = serializers.FloatField(required=False, min_value=0)
    meals_served = serializers.IntegerField(required=False, min_value=0)
    beneficiaries_served = serializers.IntegerField(required=False, min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True)


class CancelRequest(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)
    no_show = serializers.BooleanField(default=False)
