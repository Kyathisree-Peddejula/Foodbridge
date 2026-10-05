from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from django.db.models import Avg, Count, Sum
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import authentication_classes, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from core.mixins import TenantScopedMixin
from core.permissions import HasServiceKey, IsBusiness
from inventory.models import InventoryBatch, Product
from inventory.serializers import BatchSerializer
from predictions import client, heuristics, services
from predictions.models import PredictionRun, ReorderRecommendation
from predictions.payloads import batch_items, daily_sales, product_context, scorable_batches
from predictions.serializers import (PredictionRunSerializer, RefreshRequest, ReorderRequest, ReorderSerializer,
                                     RiskIngestRequest)



def _int_param(request, name, default, lo, hi):
    """Parse an integer query parameter, clamped to [lo, hi]; bad input → 400 instead of 500."""
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        raise ValidationError({name: "must be an integer"})

class RiskRefreshView(APIView):
    permission_classes = [IsBusiness]

    @extend_schema(tags=["predictions"], request=RefreshRequest, responses=PredictionRunSerializer,
                   summary="Score waste risk now (real-time, on demand) for my inventory")
    def post(self, request):
        s = RefreshRequest(data=request.data)
        s.is_valid(raise_exception=True)
        run, _ = services.refresh_risk(request.user.organization, batch_ids=s.validated_data.get("batch_ids"))
        return Response(PredictionRunSerializer(run).data)


class RiskSummaryView(APIView):
    permission_classes = [IsBusiness]

    @extend_schema(tags=["predictions"], responses={200: dict}, summary="Risk distribution and top risky batches")
    def get(self, request):
        qs = scorable_batches(request.user.organization).select_related("product__category")
        dist = {r["risk_level"]: r["n"] for r in qs.values("risk_level").annotate(n=Count("id"))}
        top = qs.exclude(risk_score=None).order_by("-risk_score")[:10]
        by_cat = list(qs.exclude(risk_score=None).values("product__category__name")
                      .annotate(avg_risk=Avg("risk_score"), expected_waste=Sum("expected_waste_qty"),
                                n=Count("id")).order_by("-avg_risk"))
        last = PredictionRun.objects.filter(organization=request.user.organization).first()
        return Response({
            "distribution": {k: dist.get(k, 0) for k in ["critical", "high", "medium", "low", "unknown"]},
            "top_risky": BatchSerializer(top, many=True, context={"request": request}).data,
            "by_category": [{"category": r["product__category__name"] or "Uncategorised",
                             "avg_risk": round(r["avg_risk"] or 0, 1),
                             "expected_waste": round(r["expected_waste"] or 0, 1), "batches": r["n"]} for r in by_cat],
            "last_run": PredictionRunSerializer(last).data if last else None,
        })


class ForecastView(APIView):
    permission_classes = [IsBusiness]

    @extend_schema(tags=["predictions"], parameters=[OpenApiParameter("horizon", int, default=14)],
                   responses={200: dict}, summary="Daily & weekly demand forecast for a product")
    def get(self, request, product_id):
        p = get_object_or_404(Product.objects.select_related("category"), pk=product_id,
                              organization=request.user.organization)
        horizon = _int_param(request, "horizon", 14, 1, 60)
        history = daily_sales([p.id], days=28)[p.id]
        item = {**product_context(p, request.user.organization), "recent_daily_sales": history}
        try:
            data = client.forecast(item, horizon)
        except client.MLServiceError:
            rate = heuristics.naive_rate(history)
            daily = [round(rate, 3)] * horizon
            data = {"model": "fallback-heuristic", "daily": daily,
                    "weekly": [round(sum(daily[i:i + 7]), 2) for i in range(0, horizon, 7)],
                    "lower": daily, "upper": daily}
        data["history"] = history
        data["product"] = {"id": p.id, "name": p.name, "unit": p.unit}
        return Response(data)


class ReorderViewSet(TenantScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = ReorderRecommendation.objects.select_related("product__category")
    serializer_class = ReorderSerializer
    permission_classes = [IsBusiness]
    pagination_class = None
    ordering = ["-recommended_qty"]

    @extend_schema(tags=["predictions"], summary="Latest smart reorder recommendations")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(tags=["predictions"], request=ReorderRequest, responses=ReorderSerializer(many=True),
                   summary="Generate reorder recommendations (demand forecast + shelf life + storage capacity)")
    def create(self, request):
        s = ReorderRequest(data=request.data)
        s.is_valid(raise_exception=True)
        recs = services.recommend_reorders(request.user.organization, s.validated_data.get("product_ids"))
        qs = ReorderRecommendation.objects.filter(id__in=[r.id for r in recs]).select_related("product__category")
        return Response(ReorderSerializer(qs.order_by("-recommended_qty"), many=True).data, status=201)


class PredictionRunViewSet(TenantScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PredictionRun.objects.all()
    serializer_class = PredictionRunSerializer
    permission_classes = [IsBusiness]

    @extend_schema(tags=["predictions"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


@extend_schema(tags=["predictions"], responses={200: dict}, summary="ML model status & evaluation metrics")
@api_view(["GET"])
def model_status(request):
    try:
        return Response({"online": True, **client.model_status()})
    except client.MLServiceError as exc:
        return Response({"online": False, "error": str(exc)[:200]})


# ------------------------------------------------------------------ internal (ML service → Django)
@extend_schema(tags=["internal"], responses={200: dict}, summary="All scorable batches (X-Service-Key)")
@api_view(["GET"])
@permission_classes([HasServiceKey])
def inventory_snapshot(request):
    items = batch_items(scorable_batches())
    run = PredictionRun.objects.create(source=PredictionRun.Source.SCHEDULED)
    return Response({"run_id": run.id, "items": items})


@extend_schema(tags=["internal"], request=RiskIngestRequest, responses={200: dict},
               summary="Receive scheduled batch risk scores (X-Service-Key)")
@api_view(["POST"])
@permission_classes([HasServiceKey])
def ingest_risk_scores(request):
    s = RiskIngestRequest(data=request.data)
    s.is_valid(raise_exception=True)
    run_id = request.query_params.get("run_id", "")
    run = PredictionRun.objects.filter(pk=int(run_id)).first() if run_id.isdigit() else None
    return Response(services.apply_scores(s.validated_data["results"], run))


@extend_schema(tags=["internal"], responses={200: dict},
               summary="Daily platform sales history for retraining (X-Service-Key)")
@api_view(["GET"])
@permission_classes([HasServiceKey])
def sales_history(request):
    days = _int_param(request, "days", 90, 1, 730)
    products = list(Product.objects.select_related("category", "organization"))
    sales = daily_sales([p.id for p in products], days=days)
    return Response({"days": days, "series": [
        {**product_context(p, p.organization), "organization_id": p.organization_id, "daily": sales[p.id]}
        for p in products if any(sales[p.id])]})


@extend_schema(tags=["internal"], request=None, responses={200: dict},
               summary="Run background jobs once (X-Service-Key) - for free hosting without a worker process",
               description="Runs the expiry scan, pickup reminders + listing expiry and, with `?risk=1`, "
                           "risk scoring for every business. Call it from a scheduler such as GitHub Actions cron.")
@api_view(["POST"])
@permission_classes([HasServiceKey])
@authentication_classes([])
def run_jobs(request):
    import time

    from core.management.commands.run_scheduler import expiry_job, pickups_job, risk_job
    done, t0 = {}, time.perf_counter()
    for name, job in [("expiry_scan", expiry_job), ("pickups", pickups_job)] + (
            [("risk_scoring", risk_job)] if request.query_params.get("risk") in ("1", "true") else []):
        try:
            job()
            done[name] = "ok"
        except Exception as exc:  # keep going; report per job
            done[name] = f"error: {exc}"
    return Response({"jobs": done, "seconds": round(time.perf_counter() - t0, 2)})
