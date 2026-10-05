from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.mixins import TenantScopedMixin
from core.models import Notification
from core.serializers import NotificationSerializer


@extend_schema_view(list=extend_schema(tags=["notifications"]), retrieve=extend_schema(tags=["notifications"]),
                    partial_update=extend_schema(tags=["notifications"]), update=extend_schema(tags=["notifications"]))
class NotificationViewSet(TenantScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    filterset_fields = ["kind", "is_read"]

    @extend_schema(tags=["notifications"], request=None, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        n = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"updated": n})

    @extend_schema(tags=["notifications"], responses={200: dict})
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"unread": self.get_queryset().filter(is_read=False).count()})
