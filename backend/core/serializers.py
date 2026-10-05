from rest_framework import serializers

from core.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "link", "data", "is_read", "created_at"]
        read_only_fields = ["kind", "title", "body", "link", "data", "created_at"]
