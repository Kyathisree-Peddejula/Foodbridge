from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.mixins import TenantScopedMixin
from core.permissions import IsBusiness, IsPlatformAdmin
from inventory import services
from inventory.filters import BatchFilter, TransactionFilter
from inventory.models import (BulkUpload, ExpiryAlert, ExpiryThreshold, FoodCategory, InventoryBatch,
                              POSIntegration, Product, StockTransaction)
from inventory.pos_auth import IsPOSClient, POSKeyAuthentication
from inventory.serializers import (AdjustRequest, BatchSerializer, BulkUploadSerializer, ClassifyRequest,
                                   ClassifyResponse, CSVUploadRequest, ExpiryAlertSerializer,
                                   ExpiryThresholdSerializer, FoodCategorySerializer, POSIntegrationSerializer,
                                   POSReceiptsRequest, POSSalesRequest, ProductSerializer, ScanRequest,
                                   TransactionSerializer)
from inventory.taxonomy import classify

T = StockTransaction.Type


def _tagged(tag):
    return {k: extend_schema(tags=[tag]) for k in
            ["list", "retrieve", "create", "update", "partial_update", "destroy"]}


# ------------------------------------------------------------------ taxonomy
@extend_schema_view(**_tagged("taxonomy"))
class FoodCategoryViewSet(viewsets.ModelViewSet):
    queryset = FoodCategory.objects.all()
    serializer_class = FoodCategorySerializer
    pagination_class = None
    filterset_fields = ["perishability", "storage"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "classify"):
            return [permissions.IsAuthenticated()]
        return [IsPlatformAdmin()]

    @extend_schema(tags=["taxonomy"], request=ClassifyRequest, responses=ClassifyResponse,
                   summary="Classify a product name into the food taxonomy")
    @action(detail=False, methods=["post"])
    def classify(self, request):
        s = ClassifyRequest(data=request.data)
        s.is_valid(raise_exception=True)
        cat, conf, hits = classify(s.validated_data["text"])
        return Response({"category": FoodCategorySerializer(cat).data if cat else None,
                         "confidence": conf, "matched_keywords": hits})


# ------------------------------------------------------------------ products
@extend_schema_view(**_tagged("inventory"))
class ProductViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    ordering = ["name"]
    permission_classes = [IsBusiness]
    filterset_fields = ["category", "unit", "is_active"]
    search_fields = ["name", "sku", "barcode"]
    ordering_fields = ["name", "created_at", "on_hand"]

    def get_queryset(self):
        self.queryset = Product.objects.select_related("category").annotate(
            on_hand=Coalesce(Sum("batches__quantity", filter=Q(batches__quantity__gt=0)), 0.0))
        return super().get_queryset()

    def perform_create(self, serializer):
        org = self.request.user.organization
        data = serializer.validated_data
        auto = False
        if not data.get("category"):
            cat, _, _ = classify(data["name"])
            data["category"] = cat
            auto = cat is not None
        if not data.get("sku"):
            data["sku"] = services._auto_sku(org, data["name"])
        obj = serializer.save(organization=org)
        obj.auto_classified = auto

    @extend_schema(tags=["inventory"], responses=ProductSerializer,
                   summary="Look up a product by barcode / QR payload")
    @action(detail=False, methods=["get"], url_path=r"by-barcode/(?P<code>[^/]+)")
    def by_barcode(self, request, code=None):
        p = self.get_queryset().filter(barcode=code).first()
        if not p:
            return Response({"detail": "No product with this barcode.", "barcode": code}, status=404)
        return Response(ProductSerializer(p).data)


# ------------------------------------------------------------------ batches
@extend_schema_view(**_tagged("inventory"))
class BatchViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = InventoryBatch.objects.select_related("product__category", "organization")
    serializer_class = BatchSerializer
    permission_classes = [IsBusiness]
    filterset_class = BatchFilter
    search_fields = ["product__name", "product__sku", "batch_code", "storage_location"]
    ordering_fields = ["expiry_date", "risk_score", "quantity", "received_date"]

    def create(self, request, *args, **kwargs):
        """Receive stock: creates the batch *and* a purchase transaction."""
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if d["product"].organization_id != request.user.organization_id:
            raise ValidationError({"product": "Unknown product."})
        if d["quantity"] <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than 0."})
        if d.get("expiry_date") and d.get("received_date") and d["expiry_date"] < d["received_date"]:
            raise ValidationError({"expiry_date": "Expiry date cannot be before the received date."})
        batch = services.receive_stock(
            d["product"], d["quantity"], expiry_date=d.get("expiry_date"), received_date=d.get("received_date"),
            location=d.get("storage_location", ""), user=request.user)
        return Response(BatchSerializer(batch, context={"request": request}).data, status=201)

    @extend_schema(tags=["inventory"], request=AdjustRequest, responses=BatchSerializer,
                   summary="Remove quantity from a batch (sold, wasted, donated or corrected)")
    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        batch = self.get_object()
        s = AdjustRequest(data=request.data)
        s.is_valid(raise_exception=True)
        if batch.quantity <= 0:
            raise ValidationError({"quantity": "This batch has no stock left."})
        services.consume_stock(batch.product, min(s.validated_data["quantity"], batch.quantity),
                               s.validated_data["reason"], batch=batch, user=request.user,
                               note=s.validated_data.get("note", ""))
        batch.refresh_from_db()
        return Response(BatchSerializer(batch, context={"request": request}).data)


@extend_schema_view(list=extend_schema(tags=["inventory"]), retrieve=extend_schema(tags=["inventory"]),
                    create=extend_schema(tags=["inventory"]))
class TransactionViewSet(TenantScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = StockTransaction.objects.select_related("product")
    serializer_class = TransactionSerializer
    permission_classes = [IsBusiness]
    filterset_class = TransactionFilter
    search_fields = ["product__name", "reference"]

    def create(self, request, *args, **kwargs):
        """Record a movement. purchase → creates a batch; sale/waste/donation → FIFO deduction."""
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        when = d.get("occurred_at") or timezone.now()
        if d["txn_type"] == T.PURCHASE:
            services.receive_stock(d["product"], d["quantity"], unit_cost=d.get("unit_price"),
                                   user=request.user, occurred_at=when, reference=d.get("reference", ""))
        else:
            services.consume_stock(d["product"], d["quantity"], d["txn_type"], unit_price=d.get("unit_price", 0),
                                   user=request.user, occurred_at=when, reference=d.get("reference", ""),
                                   note=d.get("note", ""))
        return Response({"detail": "Recorded"}, status=201)


# ------------------------------------------------------------------ CSV upload & scan
class CSVUploadView(APIView):
    permission_classes = [IsBusiness]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(tags=["inventory"], request={"multipart/form-data": CSVUploadRequest},
                   responses={201: BulkUploadSerializer},
                   summary="Bulk upload inventory (mode=inventory) or sales history (mode=transactions)")
    def post(self, request):
        s = CSVUploadRequest(data=request.data)
        s.is_valid(raise_exception=True)
        f = s.validated_data["file"]
        if f.size > 5 * 1024 * 1024:
            raise ValidationError({"file": "CSV files are limited to 5 MB - split larger files."})
        result = services.import_csv(request.user.organization, f, mode=s.validated_data["mode"],
                                     user=request.user, file_name=f.name)
        return Response(BulkUploadSerializer(result).data, status=201)


@extend_schema(tags=["inventory"], parameters=[OpenApiParameter("mode", str, enum=["inventory", "transactions"])],
               responses={(200, "text/csv"): str}, summary="Download a CSV template")
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def csv_template(request):
    mode = request.query_params.get("mode", "inventory")
    resp = HttpResponse(services.csv_template(mode), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="foodbridge_{mode}_template.csv"'
    return resp


@extend_schema_view(list=extend_schema(tags=["inventory"]))
class UploadHistoryViewSet(TenantScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = BulkUpload.objects.all()
    serializer_class = BulkUploadSerializer
    permission_classes = [IsBusiness]


class ScanView(APIView):
    permission_classes = [IsBusiness]

    @extend_schema(tags=["inventory"], request=ScanRequest, responses={200: dict},
                   summary="Apply a barcode / QR scan: receive, sell, waste or remove stock")
    def post(self, request):
        s = ScanRequest(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            product, info = services.apply_scan(request.user.organization, user=request.user, **d)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        product = Product.objects.annotate(on_hand=Coalesce(Sum("batches__quantity"), 0.0)).get(pk=product.pk)
        return Response({**info, "product": ProductSerializer(product).data})


# ------------------------------------------------------------------ expiry
@extend_schema_view(**_tagged("expiry"))
class ExpiryThresholdViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = ExpiryThreshold.objects.select_related("category")
    serializer_class = ExpiryThresholdSerializer
    permission_classes = [IsBusiness]
    pagination_class = None


@extend_schema_view(list=extend_schema(tags=["expiry"]), retrieve=extend_schema(tags=["expiry"]))
class ExpiryAlertViewSet(TenantScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    queryset = ExpiryAlert.objects.select_related("batch__product__category")
    serializer_class = ExpiryAlertSerializer
    permission_classes = [IsBusiness]
    filterset_fields = ["level", "is_acknowledged"]

    @extend_schema(tags=["expiry"], request=None, responses=ExpiryAlertSerializer)
    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        alert.is_acknowledged = True
        alert.save(update_fields=["is_acknowledged"])
        return Response(ExpiryAlertSerializer(alert).data)

    @extend_schema(tags=["expiry"], request=None, responses={200: dict},
                   summary="Run the expiry engine now for my organization")
    @action(detail=False, methods=["post"])
    def scan(self, request):
        return Response(services.run_expiry_scan(request.user.organization))


# ------------------------------------------------------------------ POS integration
@extend_schema_view(**_tagged("pos"))
class POSIntegrationViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = POSIntegration.objects.all()
    serializer_class = POSIntegrationSerializer
    permission_classes = [IsBusiness]
    pagination_class = None

    @extend_schema(tags=["pos"], request=None, responses=POSIntegrationSerializer)
    @action(detail=True, methods=["post"], url_path="rotate-key")
    def rotate_key(self, request, pk=None):
        integ = self.get_object()
        integ.rotate()
        return Response(POSIntegrationSerializer(integ).data)


class _POSBase(APIView):
    authentication_classes = [POSKeyAuthentication]
    permission_classes = [IsPOSClient]
    throttle_scope = "pos"
    throttle_classes = [ScopedRateThrottle]

    def touch(self, n):
        integ = self.request.auth
        integ.last_sync_at = timezone.now()
        integ.events_received += n
        integ.save(update_fields=["last_sync_at", "events_received"])

    def find(self, line):
        org = self.request.auth.organization
        q = Q()
        if line.get("sku"):
            q |= Q(sku__iexact=line["sku"])
        if line.get("barcode"):
            q |= Q(barcode=line["barcode"])
        return Product.objects.filter(q, organization=org).first()


class POSProductsView(_POSBase):
    @extend_schema(tags=["pos"], responses=ProductSerializer(many=True), summary="Catalogue for the POS terminal")
    def get(self, request):
        qs = Product.objects.filter(organization=request.auth.organization, is_active=True).annotate(
            on_hand=Coalesce(Sum("batches__quantity"), 0.0))
        return Response(ProductSerializer(qs, many=True).data)


class POSSalesView(_POSBase):
    @extend_schema(tags=["pos"], request=POSSalesRequest, responses={200: dict},
                   summary="Push sales from the POS (deducts stock FIFO, idempotent on reference)")
    def post(self, request):
        s = POSSalesRequest(data=request.data)
        s.is_valid(raise_exception=True)
        results = []
        for line in s.validated_data["transactions"]:
            p = self.find(line)
            ref = line.get("reference", "")
            if not p:
                results.append({"sku": line.get("sku"), "barcode": line.get("barcode"), "status": "unknown_product"})
                continue
            if ref and StockTransaction.objects.filter(product=p, reference=ref, source="pos",
                                                       txn_type=T.SALE).exists():
                results.append({"sku": p.sku, "reference": ref, "status": "duplicate_ignored"})
                continue
            services.consume_stock(p, line["quantity"], T.SALE, unit_price=line.get("unit_price", 0),
                                   source="pos", reference=ref, occurred_at=line.get("occurred_at"))
            results.append({"sku": p.sku, "reference": ref, "status": "recorded"})
        self.touch(len(results))
        return Response({"processed": len(results), "results": results})


class POSReceiptsView(_POSBase):
    @extend_schema(tags=["pos"], request=POSReceiptsRequest, responses={200: dict},
                   summary="Push goods received / purchase orders (creates batches)")
    def post(self, request):
        s = POSReceiptsRequest(data=request.data)
        s.is_valid(raise_exception=True)
        org = request.auth.organization
        out = []
        for line in s.validated_data["items"]:
            try:
                p = self.find(line) or services.get_or_create_product(
                    org, name=line.get("name"), sku=line.get("sku"), barcode=line.get("barcode"),
                    category=line.get("category"), unit_cost=line.get("unit_cost"))[0]
            except ValueError as exc:
                out.append({"status": "error", "error": str(exc)})
                continue
            b = services.receive_stock(p, line["quantity"], expiry_date=line.get("expiry_date"),
                                       unit_cost=line.get("unit_cost"), source="pos",
                                       reference=line.get("reference", ""))
            out.append({"sku": p.sku, "batch_id": b.id, "expiry_date": b.expiry_date, "status": "received"})
        self.touch(len(out))
        services.run_expiry_scan(org)
        return Response({"processed": len(out), "results": out})
