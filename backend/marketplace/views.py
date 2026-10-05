from datetime import datetime, time, timedelta

from django.db.models import Count, FloatField, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.models import Organization
from core.permissions import IsNGO, is_platform_admin
from inventory.models import InventoryBatch
from inventory.serializers import BatchSerializer
from inventory.taxonomy import classify
from marketplace import services
from marketplace.matching import rank_ngos
from core.cache import bump
from marketplace.models import Match, NGORequirement, Pickup, SurplusListing
from marketplace.serializers import (CancelRequest, ClaimRequest, CollectRequest, CompleteRequest, FromBatchRequest,
                                     ListingSerializer, MatchSerializer, OfferRequest, PickupSerializer,
                                     RequirementSerializer, RescheduleRequest)


def _tags(tag):
    return {k: extend_schema(tags=[tag]) for k in ["list", "retrieve", "create", "update", "partial_update", "destroy"]}



def with_pickup_stats(qs):
    """Annotate reserved kg and live pickup count via correlated subqueries (removes 2 queries per listing).
    Subqueries (not joins) so later filters on pickups__ cannot distort the sums."""
    base = Pickup.objects.filter(listing=OuterRef("pk")).order_by().values("listing")
    reserved = base.filter(status__in=SurplusListing.ACTIVE_PICKUP_STATES).annotate(s=Sum("quantity_kg")).values("s")
    live = base.exclude(status__in=["cancelled", "no_show"]).annotate(n=Count("id")).values("n")
    return qs.annotate(reserved_kg_annot=Subquery(reserved, output_field=FloatField()),
                       pickups_count_annot=Coalesce(Subquery(live, output_field=IntegerField()), 0))


def _err(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _slot(d, listing):
    w = d.get("window")
    if w:
        if w.listing_id != listing.id:
            raise ValidationError({"window": "This window belongs to another listing."})
        return w.start, w.end
    if not d.get("scheduled_start") or not d.get("scheduled_end"):
        raise ValidationError({"window": "Choose an availability window or give scheduled_start and scheduled_end."})
    return d["scheduled_start"], d["scheduled_end"]


@extend_schema_view(**_tags("marketplace"))
class ListingViewSet(viewsets.ModelViewSet):
    """Donors manage their own listings; NGOs see available listings (the live donation feed)."""
    serializer_class = ListingSerializer
    filterset_fields = ["status", "category", "requires_refrigeration"]
    search_fields = ["title", "description", "donor__name"]
    ordering_fields = ["created_at", "expiry_date", "quantity_kg"]

    def get_queryset(self):
        u = self.request.user
        qs = with_pickup_stats(SurplusListing.objects.select_related("donor", "category")
                               .prefetch_related("windows", "matches"))
        if getattr(self, "swagger_fake_view", False) or is_platform_admin(u):
            return qs
        org = u.organization
        if org is None:
            return qs.none()
        if org.org_type == "business":
            return qs.filter(donor=org)
        return qs.filter(Q(status="available") | Q(pickups__ngo=org)).distinct()

    def _require_donor(self, listing=None):
        org = self.request.user.organization
        if is_platform_admin(self.request.user):
            return
        if not org or org.org_type != "business" or (listing and listing.donor_id != org.id):
            raise PermissionDenied("Only the donating business can do this.")

    def perform_create(self, serializer):
        self._require_donor()
        org = self.request.user.organization
        d = serializer.validated_data
        windows = d.pop("windows", [])
        if not d.get("category"):
            d["category"] = classify(d["title"] + " " + d.get("description", ""))[0]
        cat = d.get("category")
        listing = serializer.save(
            donor=org, created_by=self.request.user,
            pickup_address=d.get("pickup_address") or org.address,
            latitude=d.get("latitude") or org.latitude, longitude=d.get("longitude") or org.longitude,
            requires_refrigeration=d.get("requires_refrigeration", bool(cat and cat.storage in ("chilled", "frozen"))))
        services.add_windows(listing, windows)
        services.compute_matches(listing)

    def perform_update(self, serializer):
        self._require_donor(serializer.instance)
        listing = serializer.save()
        services.compute_matches(listing)

    def perform_destroy(self, instance):
        self._require_donor(instance)
        if instance.pickups.filter(status__in=["confirmed", "in_transit", "completed"]).exists():
            raise ValidationError("Listings with scheduled or completed pickups cannot be deleted; cancel instead.")
        if instance.batch and instance.batch.status == InventoryBatch.Status.LISTED:
            instance.batch.status = InventoryBatch.Status.ACTIVE
            instance.batch.save(update_fields=["status"])
        instance.delete()

    # ---- donor actions
    @extend_schema(tags=["marketplace"], request=FromBatchRequest, responses={201: ListingSerializer},
                   summary="List surplus straight from an inventory batch (defaults to predicted unsold quantity)")
    @action(detail=False, methods=["post"], url_path="from-batch")
    def from_batch(self, request):
        self._require_donor()
        s = FromBatchRequest(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        batch = d.pop("batch")
        if batch.organization_id != request.user.organization_id:
            raise PermissionDenied("Batch belongs to another organization.")
        try:
            listing = services.listing_from_batch(batch, user=request.user, windows=d.pop("windows", []), **d)
        except ValueError as exc:
            return _err(exc)
        services.compute_matches(listing)
        return Response(ListingSerializer(listing, context={"request": request}).data, status=201)

    @extend_schema(tags=["marketplace"], responses=BatchSerializer(many=True),
                   summary="AI donation suggestions: high-risk batches that are not yet listed")
    @action(detail=False, methods=["get"])
    def suggestions(self, request):
        self._require_donor()
        qs = (InventoryBatch.objects.filter(organization=request.user.organization, quantity__gt=0,
                                            risk_level__in=["high", "critical"], expiry_date__gte=timezone.localdate())
              .exclude(status__in=["listed", "depleted"]).select_related("product__category").order_by("-risk_score"))
        return Response(BatchSerializer(qs[:20], many=True, context={"request": request}).data)

    @extend_schema(tags=["marketplace"], responses=MatchSerializer(many=True),
                   summary="Ranked NGO matches for this listing (AI matching engine)")
    @action(detail=True, methods=["get"])
    def matches(self, request, pk=None):
        listing = self.get_object()
        self._require_donor(listing)
        if request.query_params.get("refresh") == "1" or not listing.matches.exists():
            services.compute_matches(listing)
        return Response(MatchSerializer(listing.matches.select_related("ngo").order_by("-score"), many=True).data)

    @extend_schema(tags=["marketplace"], request=OfferRequest, responses={201: PickupSerializer},
                   summary="Offer the listing to a specific NGO (donor-initiated pickup)")
    @action(detail=True, methods=["post"])
    def offer(self, request, pk=None):
        listing = self.get_object()
        self._require_donor(listing)
        s = OfferRequest(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        ngo = Organization.objects.filter(pk=d.pop("ngo"), org_type="ngo").first()
        if not ngo:
            raise ValidationError({"ngo": "Unknown NGO"})
        start, end = _slot(d, listing)
        try:
            p = services.create_pickup(listing, ngo, quantity_kg=d.pop("quantity_kg"), start=start, end=end,
                                       initiated_by="donor", **d)
        except ValueError as exc:
            return _err(exc)
        return Response(PickupSerializer(p, context={"request": request}).data, status=201)

    @extend_schema(tags=["marketplace"], request=None, responses=ListingSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        listing = self.get_object()
        self._require_donor(listing)
        for p in listing.pickups.filter(status__in=["requested", "confirmed"]):
            services.cancel(p, "donor", "Donor withdrew the listing")
        listing.status = SurplusListing.Status.CANCELLED
        listing.save(update_fields=["status"])
        return Response(ListingSerializer(listing, context={"request": request}).data)

    # ---- NGO actions
    @extend_schema(tags=["marketplace"], parameters=[
        OpenApiParameter("category", str, description="taxonomy slug"),
        OpenApiParameter("max_distance_km", float), OpenApiParameter("min_score", float)],
        responses=ListingSerializer(many=True),
        summary="Live donation feed for my NGO, ranked by AI match score")
    @action(detail=False, methods=["get"], permission_classes=[IsNGO])
    def feed(self, request):
        org = request.user.organization
        qs = (SurplusListing.objects.filter(status="available", expiry_date__gte=timezone.localdate())
              .select_related("donor", "category").prefetch_related("windows"))
        if c := request.query_params.get("category"):
            qs = qs.filter(category__slug=c)
        qs = qs.exclude(matches__ngo=org, matches__status=Match.Status.DECLINED)
        scored = set(Match.objects.filter(ngo=org, listing__in=qs).values_list("listing_id", flat=True))
        for l in qs[:200]:
            if l.id in scored:
                continue
            ranked = rank_ngos(l, limit=1, only_ngo=org)
            if ranked:  # NGO passes the hard constraints
                r = ranked[0]
                Match.objects.update_or_create(listing=l, ngo=org, defaults=dict(
                    requirement=r["requirement"], score=r["score"], distance_km=r["distance_km"],
                    breakdown=r["breakdown"], reasons=r["reasons"]))
        listings = list(qs.prefetch_related(Prefetch("matches", queryset=Match.objects.filter(ngo=org)))[:200])
        try:
            maxd = float(request.query_params.get("max_distance_km") or 0) or None
            mins = float(request.query_params.get("min_score") or 0)
        except ValueError:
            raise ValidationError({"detail": "max_distance_km and min_score must be numbers"})
        ctx = {"request": request}
        data = ListingSerializer(listings, many=True, context=ctx).data
        data = [d for d in data if d["remaining_kg"] > 0 and d["match_score"] is not None and d["match_score"] >= mins
                and (not maxd or d["distance_km"] is None or d["distance_km"] <= maxd)]
        data.sort(key=lambda d: (-(d["match_score"] or 0), d["days_to_expiry"]))
        return Response(data)

    @extend_schema(tags=["marketplace"], request=ClaimRequest, responses={201: PickupSerializer},
                   summary="Claim (part of) a listing and request a pickup slot")
    @action(detail=True, methods=["post"], permission_classes=[IsNGO])
    def claim(self, request, pk=None):
        listing = self.get_object()
        s = ClaimRequest(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        start, end = _slot(d, listing)
        d.pop("window", None)
        d.pop("scheduled_start", None)
        d.pop("scheduled_end", None)
        try:
            p = services.create_pickup(listing, request.user.organization, quantity_kg=d.pop("quantity_kg"),
                                       start=start, end=end, initiated_by="ngo", **d)
        except ValueError as exc:
            return _err(exc)
        return Response(PickupSerializer(p, context={"request": request}).data, status=201)

    @extend_schema(tags=["marketplace"], request=None, responses={200: dict},
                   summary="Hide a matched listing from my feed")
    @action(detail=True, methods=["post"], permission_classes=[IsNGO])
    def decline(self, request, pk=None):
        Match.objects.filter(listing_id=pk, ngo=request.user.organization).update(status=Match.Status.DECLINED)
        bump(request.user.organization_id)
        return Response({"detail": "Declined"})


@extend_schema_view(**_tags("marketplace"))
class RequirementViewSet(viewsets.ModelViewSet):
    """What an NGO needs: food types, quantity range, distance, dietary and pickup constraints."""
    serializer_class = RequirementSerializer
    permission_classes = [IsNGO]
    pagination_class = None

    def get_queryset(self):
        qs = NGORequirement.objects.prefetch_related("categories")
        return qs if getattr(self, "swagger_fake_view", False) or is_platform_admin(self.request.user) else qs.filter(ngo=self.request.user.organization)

    def perform_create(self, serializer):
        serializer.save(ngo=self.request.user.organization)


@extend_schema_view(list=extend_schema(tags=["pickups"]), retrieve=extend_schema(tags=["pickups"]))
class PickupViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PickupSerializer
    filterset_fields = ["status", "ngo", "listing"]
    ordering_fields = ["scheduled_start", "created_at"]

    def get_queryset(self):
        qs = Pickup.objects.select_related("listing__donor", "listing__category", "ngo")
        u = self.request.user
        if getattr(self, "swagger_fake_view", False) or is_platform_admin(u):
            return qs
        return qs.filter(Q(ngo=u.organization) | Q(listing__donor=u.organization))

    def _side(self, p):
        org_id = self.request.user.organization_id
        if p.listing.donor_id == org_id:
            return "donor"
        if p.ngo_id == org_id:
            return "ngo"
        raise PermissionDenied("Not your pickup")

    def _run(self, fn, *a, **kw):
        try:
            p = fn(*a, **kw)
        except ValueError as exc:
            return _err(exc)
        p.refresh_from_db()
        return Response(PickupSerializer(p, context={"request": self.request}).data)

    @extend_schema(tags=["pickups"], request=None, responses=PickupSerializer,
                   summary="Confirm the pickup from my side (both donor and NGO must confirm)")
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        p = self.get_object()
        return self._run(services.confirm, p, self._side(p))

    @extend_schema(tags=["pickups"], request=RescheduleRequest, responses=PickupSerializer)
    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        p = self.get_object()
        s = RescheduleRequest(data=request.data)
        s.is_valid(raise_exception=True)
        return self._run(services.reschedule, p, self._side(p), s.validated_data["scheduled_start"],
                         s.validated_data["scheduled_end"])

    @extend_schema(tags=["pickups"], request=CollectRequest, responses=PickupSerializer,
                   summary="Mark food as collected (in transit) — deducts donor stock")
    @action(detail=True, methods=["post"])
    def collect(self, request, pk=None):
        p = self.get_object()
        self._side(p)
        s = CollectRequest(data=request.data)
        s.is_valid(raise_exception=True)
        return self._run(services.mark_collected, p, **s.validated_data)

    @extend_schema(tags=["pickups"], request=CompleteRequest, responses=PickupSerializer,
                   summary="NGO confirms delivery and records beneficiary impact")
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        p = self.get_object()
        if self._side(p) != "ngo" and not is_platform_admin(request.user):
            raise PermissionDenied("Only the receiving NGO can complete a pickup")
        s = CompleteRequest(data=request.data)
        s.is_valid(raise_exception=True)
        return self._run(services.complete, p, **s.validated_data)

    @extend_schema(tags=["pickups"], request=CancelRequest, responses=PickupSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        p = self.get_object()
        side = self._side(p)
        s = CancelRequest(data=request.data)
        s.is_valid(raise_exception=True)
        if s.validated_data["no_show"] and side != "donor":
            raise PermissionDenied("Only the donor can report a no-show")
        return self._run(services.cancel, p, side, s.validated_data.get("reason", ""), s.validated_data["no_show"])

    @extend_schema(tags=["pickups"], parameters=[OpenApiParameter("start", str, description="YYYY-MM-DD"),
                                                 OpenApiParameter("end", str, description="YYYY-MM-DD")],
                   responses={200: dict}, summary="Calendar feed of pickups between two dates")
    @action(detail=False, methods=["get"])
    def calendar(self, request):
        today = timezone.localdate()
        start = parse_date(request.query_params.get("start", "")) or today.replace(day=1)
        end = parse_date(request.query_params.get("end", "")) or (start + timedelta(days=42))
        tz = timezone.get_current_timezone()
        qs = self.get_queryset().filter(
            scheduled_start__gte=datetime.combine(start, time.min, tz),
            scheduled_start__lt=datetime.combine(end + timedelta(days=1), time.min, tz))
        events = [{"id": p.id, "title": p.listing.title, "start": p.scheduled_start, "end": p.scheduled_end,
                   "status": p.status, "quantity_kg": p.quantity_kg, "donor": p.listing.donor.name,
                   "ngo": p.ngo.name, "address": p.listing.pickup_address} for p in qs]
        return Response({"start": start, "end": end, "events": events})
