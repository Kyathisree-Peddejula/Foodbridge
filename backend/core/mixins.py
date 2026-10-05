from core.permissions import is_platform_admin


class TenantScopedMixin:
    """Restricts a ModelViewSet's queryset to the caller's organization.

    Platform admins see all tenants. Set `tenant_field` when the organization FK
    lives under another name or relation (e.g. "product__organization").
    """
    tenant_field = "organization"

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return qs.none()
        user = self.request.user
        if is_platform_admin(user):
            org = self.request.query_params.get("organization")
            return qs.filter(**{f"{self.tenant_field}_id": org}) if org else qs
        if not user.organization_id:
            return qs.none()
        return qs.filter(**{f"{self.tenant_field}_id": user.organization_id})

    def perform_create(self, serializer):
        if self.tenant_field == "organization":
            serializer.save(organization=self.request.user.organization)
        else:
            serializer.save()
