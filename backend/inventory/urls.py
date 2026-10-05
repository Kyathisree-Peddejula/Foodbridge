from django.urls import path
from rest_framework.routers import DefaultRouter

from inventory import views

router = DefaultRouter()
router.register("taxonomy/categories", views.FoodCategoryViewSet, basename="category")
router.register("inventory/products", views.ProductViewSet, basename="product")
router.register("inventory/batches", views.BatchViewSet, basename="batch")
router.register("inventory/transactions", views.TransactionViewSet, basename="transaction")
router.register("inventory/uploads", views.UploadHistoryViewSet, basename="upload")
router.register("expiry/thresholds", views.ExpiryThresholdViewSet, basename="threshold")
router.register("expiry/alerts", views.ExpiryAlertViewSet, basename="alert")
router.register("pos/integrations", views.POSIntegrationViewSet, basename="pos-integration")

urlpatterns = [
    path("inventory/upload-csv/", views.CSVUploadView.as_view(), name="upload-csv"),
    path("inventory/csv-template/", views.csv_template, name="csv-template"),
    path("inventory/scan/", views.ScanView.as_view(), name="scan"),
    path("pos/v1/products/", views.POSProductsView.as_view(), name="pos-products"),
    path("pos/v1/sales/", views.POSSalesView.as_view(), name="pos-sales"),
    path("pos/v1/receipts/", views.POSReceiptsView.as_view(), name="pos-receipts"),
] + router.urls
