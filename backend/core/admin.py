from django.contrib import admin

from core.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "organization", "kind", "is_read", "created_at"]
    list_filter = ["kind", "is_read"]
