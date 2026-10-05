from django.contrib import admin

from marketplace.models import AvailabilityWindow, Match, NGORequirement, Pickup, SurplusListing


class WindowInline(admin.TabularInline):
    model = AvailabilityWindow
    extra = 0


@admin.register(SurplusListing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ["title", "donor", "quantity_kg", "expiry_date", "status"]
    list_filter = ["status", "category"]
    inlines = [WindowInline]


@admin.register(Pickup)
class PickupAdmin(admin.ModelAdmin):
    list_display = ["listing", "ngo", "quantity_kg", "scheduled_start", "status"]
    list_filter = ["status"]


admin.site.register([NGORequirement, Match])
