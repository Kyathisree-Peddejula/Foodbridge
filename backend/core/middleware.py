"""Row-level multi-tenancy: every request is bound to the caller's organization."""
from rest_framework_simplejwt.authentication import JWTAuthentication


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt = JWTAuthentication()

    def __call__(self, request):
        request.tenant = None
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            try:
                result = self.jwt.authenticate(request)
                if result:
                    user = result[0]
            except Exception:  # invalid token: DRF will reject it later
                user = None
        if user is not None and getattr(user, "is_authenticated", False):
            request.tenant = getattr(user, "organization", None)
        return self.get_response(request)
