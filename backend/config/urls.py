from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from django.http import JsonResponse
from django.views.generic import RedirectView


def health(_request):
    return JsonResponse({"status": "ok", "service": "foodbridge-api"})


urlpatterns = [
    path("", RedirectView.as_view(url="/api/docs/", permanent=False)),
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/", include("accounts.urls")),
    path("api/", include("core.urls")),
    path("api/", include("inventory.urls")),
    path("api/", include("predictions.urls")),
    path("api/", include("marketplace.urls")),
    path("api/", include("analytics.urls")),
]
