from django.db import models


class PredictionRun(models.Model):
    class Source(models.TextChoices):
        ON_DEMAND = "on_demand", "On demand"
        SCHEDULED = "scheduled", "Scheduled batch"

    organization = models.ForeignKey("accounts.Organization", null=True, blank=True, on_delete=models.CASCADE,
                                     related_name="prediction_runs")
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.ON_DEMAND)
    engine = models.CharField(max_length=24, default="ml-service", help_text="ml-service or fallback-heuristic")
    status = models.CharField(max_length=12, default="running")
    items_scored = models.PositiveIntegerField(default=0)
    high_risk_items = models.PositiveIntegerField(default=0)
    detail = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]


class ReorderRecommendation(models.Model):
    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="reorders")
    product = models.ForeignKey("inventory.Product", on_delete=models.CASCADE, related_name="reorders")
    current_stock = models.FloatField()
    forecast_demand = models.FloatField(help_text="Demand over lead time + review period")
    safety_stock = models.FloatField(default=0)
    recommended_qty = models.FloatField()
    max_by_shelf_life = models.FloatField(null=True, blank=True)
    max_by_capacity = models.FloatField(null=True, blank=True)
    naive_order_qty = models.FloatField(null=True, blank=True)
    expected_waste_avoided = models.FloatField(default=0)
    urgency = models.CharField(max_length=12, default="normal")
    rationale = models.TextField(blank=True)
    engine = models.CharField(max_length=24, default="ml-service")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
