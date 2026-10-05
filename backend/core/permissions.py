from django.conf import settings
from rest_framework.permissions import BasePermission


def is_platform_admin(user):
    return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, "role", "") == "admin"))


class IsBusiness(BasePermission):
    message = "This action is available to food business accounts."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (is_platform_admin(u) or
                    (u.organization and u.organization.org_type == "business")))


class IsNGO(BasePermission):
    message = "This action is available to NGO / recipient accounts."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (is_platform_admin(u) or
                    (u.organization and u.organization.org_type == "ngo")))


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_platform_admin(request.user)


class HasServiceKey(BasePermission):
    """Service-to-service auth for the ML microservice (header X-Service-Key)."""
    message = "Missing or invalid X-Service-Key."

    def has_permission(self, request, view):
        return request.headers.get("X-Service-Key") == settings.SERVICE_API_KEY
