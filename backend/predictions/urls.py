from django.urls import path
from rest_framework.routers import DefaultRouter

from predictions import views

router = DefaultRouter()
router.register("predictions/reorder", views.ReorderViewSet, basename="reorder")
router.register("predictions/runs", views.PredictionRunViewSet, basename="prediction-run")

urlpatterns = [
    path("predictions/risk/refresh/", views.RiskRefreshView.as_view()),
    path("predictions/risk/summary/", views.RiskSummaryView.as_view()),
    path("predictions/forecast/<int:product_id>/", views.ForecastView.as_view()),
    path("predictions/model-status/", views.model_status),
    path("internal/inventory-snapshot/", views.inventory_snapshot),
    path("internal/risk-scores/", views.ingest_risk_scores),
    path("internal/sales-history/", views.sales_history),
    path("internal/run-jobs/", views.run_jobs),
] + router.urls
