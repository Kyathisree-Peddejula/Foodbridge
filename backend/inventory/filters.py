from datetime import date, timedelta

import django_filters

from inventory.models import InventoryBatch, StockTransaction
from django.utils import timezone


class BatchFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="product__category__slug")
    expiring_within = django_filters.NumberFilter(method="filter_expiring", label="Days to expiry <= N")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    min_risk = django_filters.NumberFilter(field_name="risk_score", lookup_expr="gte")

    class Meta:
        model = InventoryBatch
        fields = ["status", "risk_level", "product", "category", "storage_location"]

    def filter_expiring(self, qs, name, value):
        return qs.filter(expiry_date__lte=timezone.localdate() + timedelta(days=int(value)))

    def filter_in_stock(self, qs, name, value):
        return qs.filter(quantity__gt=0) if value else qs.filter(quantity__lte=0)


class TransactionFilter(django_filters.FilterSet):
    since = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    until = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lte")

    class Meta:
        model = StockTransaction
        fields = ["txn_type", "product", "source", "since", "until"]
