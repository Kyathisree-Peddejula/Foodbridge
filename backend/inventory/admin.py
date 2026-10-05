from django.contrib import admin

from inventory import models as m


@admin.register(m.FoodCategory)
class FoodCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "perishability", "storage", "default_shelf_life_days", "warning_days", "critical_days"]


@admin.register(m.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "sku", "barcode", "category", "organization"]
    list_filter = ["category", "organization"]
    search_fields = ["name", "sku", "barcode"]


@admin.register(m.InventoryBatch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ["product", "quantity", "expiry_date", "status", "risk_level", "risk_score", "organization"]
    list_filter = ["status", "risk_level", "organization"]


@admin.register(m.StockTransaction)
class TxnAdmin(admin.ModelAdmin):
    list_display = ["product", "txn_type", "quantity", "occurred_at", "source", "organization"]
    list_filter = ["txn_type", "source"]


admin.site.register([m.ExpiryAlert, m.ExpiryThreshold, m.POSIntegration, m.BulkUpload])
