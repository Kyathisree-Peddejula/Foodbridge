"""Bump cache versions whenever data behind a dashboard changes."""
from django.db.models.signals import m2m_changed, post_delete, post_save

from core.cache import bump


def _orgs(instance):
    from inventory.models import ExpiryAlert, InventoryBatch, Product, StockTransaction
    from marketplace.models import AvailabilityWindow, Match, NGORequirement, Pickup, SurplusListing
    if isinstance(instance, (InventoryBatch, StockTransaction, Product, ExpiryAlert)):
        return [instance.organization_id]
    if isinstance(instance, SurplusListing):
        return [instance.donor_id]
    if isinstance(instance, AvailabilityWindow):
        return [instance.listing.donor_id]
    if isinstance(instance, Pickup):
        return [instance.ngo_id, instance.listing.donor_id]
    if isinstance(instance, Match):
        return [instance.ngo_id, instance.listing.donor_id]
    if isinstance(instance, NGORequirement):
        return [instance.ngo_id]
    return None


def _handler(sender, instance, **kwargs):
    orgs = _orgs(instance)
    if orgs is not None:
        bump(*orgs)


def connect():
    for sig in (post_save, post_delete):
        sig.connect(_handler, dispatch_uid=f"fb-cache-{sig}")
    m2m_changed.connect(_handler, dispatch_uid="fb-cache-m2m")
