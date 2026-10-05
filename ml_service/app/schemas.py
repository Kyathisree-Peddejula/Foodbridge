from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ProductContext(BaseModel):
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    unit: Optional[str] = "units"
    category_slug: Optional[str] = Field(None, examples=["dairy"])
    perishability: Optional[str] = Field("medium", examples=["high"])
    shelf_life_days: Optional[int] = 7
    fr_store_id: Optional[int] = None
    fr_product_id: Optional[int] = None
    fr_first_category_id: Optional[int] = None
    recent_daily_sales: list[float] = Field(default_factory=list, description="Oldest → yesterday (ideally 28 days)")


class ForecastRequest(ProductContext):
    horizon_days: int = Field(14, ge=1, le=60)


class ForecastResponse(BaseModel):
    model: str
    weights: dict[str, float]
    horizon_days: int
    start_date: str
    daily: list[float]
    lower: list[float]
    upper: list[float]
    weekly: list[float]
    components: dict[str, list[float]]
    expected_error_wape: float


class RiskItem(ProductContext):
    batch_id: Optional[int] = None
    organization_id: Optional[int] = None
    quantity: float = Field(..., ge=0, examples=[40])
    days_to_expiry: int = Field(..., examples=[2])
    expiry_date: Optional[str] = None
    unit_weight_kg: Optional[float] = None


class RiskResult(BaseModel):
    batch_id: Optional[int]
    product_id: Optional[int]
    risk_score: float
    risk_level: str
    predicted_demand: float
    expected_waste_qty: float
    recommended_action: str
    model: str
    factors: dict[str, Any]


class RiskBatchRequest(BaseModel):
    items: list[RiskItem]


class RiskBatchResponse(BaseModel):
    results: list[RiskResult]
    summary: dict[str, Any]


class ReorderItem(ProductContext):
    current_stock: float = 0
    storage_space_per_unit: Optional[float] = 1.0


class ReorderRequest(BaseModel):
    items: list[ReorderItem]
    lead_time_days: int = 1
    review_period_days: int = 1
    storage_capacity: Optional[float] = None
    storage_used: float = 0


class ReorderResult(BaseModel):
    product_id: Optional[int]
    current_stock: float
    forecast_demand: float
    safety_stock: float
    recommended_qty: float
    max_by_shelf_life: float
    max_by_capacity: Optional[float]
    naive_order_qty: float
    expected_waste_avoided: float
    days_of_cover: Optional[float]
    urgency: str
    rationale: str
    model: str


class ReorderResponse(BaseModel):
    results: list[ReorderResult]
    constraints: dict[str, Any]


class TrainRequest(BaseModel):
    models: list[str] = Field(default_factory=lambda: ["prophet", "lstm"])
    max_series: Optional[int] = Field(None, description="Cap LSTM training series (speed)")
    epochs: Optional[int] = None
    eval_series: Optional[int] = None
