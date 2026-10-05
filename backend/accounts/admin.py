from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import Organization, User


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "org_type", "kind", "city", "is_verified", "fr_store_id"]
    list_filter = ["org_type", "kind", "is_verified"]
    search_fields = ["name", "city"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "username", "role", "organization", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (("FoodBridge", {"fields": ("role", "organization", "phone")}),)
