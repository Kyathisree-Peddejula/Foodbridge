from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed(sender, **kwargs):
    from inventory.taxonomy import ensure_taxonomy
    ensure_taxonomy()


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventory"

    def ready(self):
        post_migrate.connect(_seed, sender=self)
        from inventory import schema  # noqa: F401  (OpenAPI auth extension)
