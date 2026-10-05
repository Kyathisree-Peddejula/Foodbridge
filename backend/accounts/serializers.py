from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import Organization, User


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "org_type", "kind", "contact_email", "phone", "address", "city",
                  "latitude", "longitude", "storage_capacity_kg", "reorder_lead_time_days",
                  "daily_capacity_kg", "beneficiaries", "can_pickup", "reliability_score",
                  "fr_store_id", "fr_city_id", "is_verified", "created_at"]
        read_only_fields = ["slug", "reliability_score", "is_verified", "created_at"]


class OrganizationPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "org_type", "kind", "city", "address", "latitude", "longitude",
                  "phone", "beneficiaries", "daily_capacity_kg"]


class UserSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "phone", "role", "organization"]
        read_only_fields = ["role", "organization"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    org_type = serializers.ChoiceField(choices=Organization.OrgType.choices)
    organization_name = serializers.CharField(max_length=160)
    kind = serializers.ChoiceField(choices=Organization.BusinessKind.choices, required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    beneficiaries = serializers.IntegerField(required=False, min_value=0)
    daily_capacity_kg = serializers.FloatField(required=False, min_value=0)

    def validate_email(self, v):
        if User.objects.filter(email__iexact=v).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return v.lower()

    @transaction.atomic
    def create(self, data):
        org = Organization.objects.create(
            name=data["organization_name"], org_type=data["org_type"], kind=data.get("kind", ""),
            city=data.get("city", ""), address=data.get("address", ""), phone=data.get("phone", ""),
            latitude=data.get("latitude"), longitude=data.get("longitude"), contact_email=data["email"],
            beneficiaries=data.get("beneficiaries", 0), daily_capacity_kg=data.get("daily_capacity_kg", 200),
        )
        user = User.objects.create_user(
            username=data["email"], email=data["email"], password=data["password"],
            first_name=data.get("first_name", ""), last_name=data.get("last_name", ""),
            role=User.Role.NGO if org.org_type == "ngo" else User.Role.BUSINESS, organization=org,
        )
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = User.objects.filter(email__iexact=attrs["email"]).first()
        user = authenticate(username=user.username, password=attrs["password"]) if user else None
        if not user:
            raise serializers.ValidationError("Email or password is incorrect.")
        attrs["user"] = user
        return attrs


def tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class AuthResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()
