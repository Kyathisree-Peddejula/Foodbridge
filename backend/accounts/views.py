from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Organization
from accounts.serializers import (AuthResponseSerializer, LoginSerializer, OrganizationPublicSerializer,
                                  OrganizationSerializer, RegisterSerializer, UserSerializer, tokens_for)
from core.permissions import is_platform_admin


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["auth"], request=RegisterSerializer, responses={201: AuthResponseSerializer},
                   summary="Register a food business or NGO with its first user")
    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.save()
        return Response({**tokens_for(user), "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    throttle_scope = "login"  # brute-force protection
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["auth"], request=LoginSerializer, responses={200: AuthResponseSerializer},
                   summary="Log in with email + password, returns JWT pair")
    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.validated_data["user"]
        return Response({**tokens_for(user), "user": UserSerializer(user).data})


@extend_schema(tags=["auth"])
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


@extend_schema(tags=["organizations"])
class OrganizationViewSet(viewsets.ModelViewSet):
    """Admins manage all tenants; members can view and edit their own organization."""
    serializer_class = OrganizationSerializer
    filterset_fields = ["org_type", "kind", "city"]
    search_fields = ["name", "city"]
    http_method_names = ["get", "patch", "put", "delete", "head", "options"]

    def get_queryset(self):
        u = self.request.user
        if getattr(self, "swagger_fake_view", False) or is_platform_admin(u):
            return Organization.objects.all()
        return Organization.objects.filter(pk=u.organization_id)

    @extend_schema(tags=["organizations"], responses=OrganizationSerializer)
    @action(detail=False, methods=["get", "patch"], url_path="mine")
    def mine(self, request):
        org = request.user.organization
        if request.method == "PATCH":
            s = OrganizationSerializer(org, data=request.data, partial=True)
            s.is_valid(raise_exception=True)
            s.save()
            return Response(s.data)
        return Response(OrganizationSerializer(org).data)

    @extend_schema(tags=["organizations"], responses=OrganizationPublicSerializer(many=True),
                   summary="Directory of verified-or-active NGOs (the NGO network)")
    @action(detail=False, methods=["get"], url_path="ngo-network")
    def ngo_network(self, request):
        qs = Organization.objects.filter(org_type="ngo").order_by("name")
        return Response(OrganizationPublicSerializer(qs, many=True).data)
