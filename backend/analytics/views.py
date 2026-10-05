from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from analytics import services
from core.cache import PLATFORM, cached
from core.permissions import IsBusiness, IsNGO, IsPlatformAdmin, is_platform_admin


@extend_schema(tags=["analytics"], responses={200: dict},
               summary="Business view: inventory health, waste-risk charts, donation tracker")
@api_view(["GET"])
@permission_classes([IsBusiness])
def business(request):
    org = request.user.organization
    return Response(cached("business", org.id, lambda: services.business_dashboard(org)))


@extend_schema(tags=["analytics"], responses={200: dict},
               summary="NGO view: incoming donations, pickup history, beneficiary impact")
@api_view(["GET"])
@permission_classes([IsNGO])
def ngo(request):
    org = request.user.organization
    return Response(cached("ngo", org.id, lambda: services.ngo_dashboard(org)))


@extend_schema(tags=["analytics"], parameters=[OpenApiParameter("scope", str, enum=["mine", "platform"])],
               responses={200: dict}, summary="Sustainability impact: food diverted, CO2e saved, meals redistributed")
@api_view(["GET"])
def impact(request):
    scope = request.query_params.get("scope", "mine")
    org = None if scope == "platform" or (is_platform_admin(request.user) and scope != "mine") \
        else request.user.organization
    data = cached("impact", org.id if org else PLATFORM, lambda: services.impact_dashboard(org))
    return Response({"scope": "platform" if org is None else "organization", **data})


@extend_schema(tags=["analytics"], responses={200: dict}, summary="Platform admin overview")
@api_view(["GET"])
@permission_classes([IsPlatformAdmin])
def admin_overview(request):
    try:
        days = max(1, min(365, int(request.query_params.get("days", 30))))
    except ValueError:
        days = 30
    return Response(cached("admin", PLATFORM, lambda: services.admin_overview(days), extra=days))
