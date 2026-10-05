from rest_framework import authentication, exceptions
from rest_framework.permissions import BasePermission

from inventory.models import POSIntegration


class POSClient:
    """Pseudo-user representing an authenticated POS terminal."""
    is_authenticated = True
    is_superuser = False
    role = "pos"

    def __init__(self, integration):
        self.integration = integration
        self.organization = integration.organization
        self.organization_id = integration.organization_id
        self.pk = None


class POSKeyAuthentication(authentication.BaseAuthentication):
    keyword = "X-POS-Key"

    def authenticate(self, request):
        key = request.headers.get(self.keyword)
        if not key:
            return None
        integ = POSIntegration.objects.select_related("organization").filter(api_key=key, is_active=True).first()
        if not integ:
            raise exceptions.AuthenticationFailed("Invalid or inactive POS key.")
        return POSClient(integ), integ

    def authenticate_header(self, request):
        return self.keyword


class IsPOSClient(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.auth, POSIntegration)
