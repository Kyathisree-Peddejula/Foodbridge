from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.models import Notification
from core.services import notify
from inventory.models import InventoryBatch, StockTransaction
from inventory.services import consume_stock
from marketplace.matching import rank_ngos, update_reliability
from marketplace.models import Match, Pickup, SurplusListing

KIND = Notification.Kind


def compute_matches(listing, notify_top=5):
    ranked = rank_ngos(listing, limit=15)
    keep = []
    for i, r in enumerate(ranked):
        m, created = Match.objects.update_or_create(
            listing=listing, ngo=r["ngo"],
            defaults=dict(requirement=r["requirement"], score=r["score"], distance_km=r["distance_km"],
                          breakdown={**r["breakdown"], "_weights": r["weights"]}, reasons=r["reasons"]))
        keep.append(m.id)
        if created and i < notify_top:
            notify(r["ngo"], f"New donation match: {listing.title}",
                   f"{listing.quantity_kg:g} kg from {listing.donor.name}, best before {listing.expiry_date}. "
                   f"Match score {r['score']:.0f}/100 · {', '.join(r['reasons'])}",
                   kind=KIND.MATCH, link=f"/feed/{listing.id}", data={"listing_id": listing.id})
    listing.matches.exclude(id__in=keep).filter(status=Match.Status.SUGGESTED).delete()
    return listing.matches.select_related("ngo").order_by("-score")


def listing_from_batch(batch, *, quantity=None, windows=(), user=None, **extra):
    if batch.quantity <= 0:
        raise ValueError("This batch has no stock left")
    if batch.expiry_date < timezone.localdate():
        raise ValueError("Expired food cannot be listed for donation")
    if batch.listings.filter(status__in=["available", "reserved"]).exists():
        raise ValueError("This batch already has an active listing")
    p = batch.product
    qty_units = quantity or batch.expected_waste_qty or batch.quantity
    qty_units = min(qty_units, batch.quantity)
    org = batch.organization
    cat = p.category
    listing = SurplusListing.objects.create(
        donor=org, batch=batch, title=extra.get("title") or f"{p.name}",
        description=extra.get("description", ""), category=cat,
        quantity_kg=round(qty_units * (p.unit_weight_kg or 1), 3), quantity_units=qty_units, unit=p.unit,
        expiry_date=batch.expiry_date, pickup_address=extra.get("pickup_address") or org.address,
        latitude=org.latitude, longitude=org.longitude, dietary_tags=extra.get("dietary_tags", []),
        requires_refrigeration=bool(cat and cat.storage in ("chilled", "frozen")),
        handling_notes=cat.handling_notes if cat else "", created_by=user,
        auto_suggested=extra.get("auto_suggested", False))
    add_windows(listing, windows)
    batch.status = InventoryBatch.Status.LISTED
    batch.save(update_fields=["status"])
    return listing


def add_windows(listing, windows):
    from marketplace.models import AvailabilityWindow
    if not windows:
        now = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        windows = [{"start": now, "end": now + timedelta(hours=4)}]
    for w in windows:
        AvailabilityWindow.objects.create(listing=listing, start=w["start"], end=w["end"])


@transaction.atomic
def create_pickup(listing, ngo, *, quantity_kg, start, end, initiated_by="ngo", **extra):
    listing = SurplusListing.objects.select_for_update().get(pk=listing.pk)
    if listing.status not in (SurplusListing.Status.AVAILABLE,):
        raise ValueError(f"Listing is {listing.get_status_display().lower()}")
    if quantity_kg > listing.remaining_kg + 1e-6:
        raise ValueError(f"Only {listing.remaining_kg:g} kg is still available")
    if end <= start:
        raise ValueError("Pickup end must be after start")
    if ngo.org_type != "ngo":
        raise ValueError("Only NGOs can receive donations")
    now = timezone.now()
    if end < now:
        raise ValueError("That pickup slot is already over - choose a future time")
    if timezone.localtime(start).date() > listing.expiry_date:
        raise ValueError(f"Pickup must happen on or before the best-before date ({listing.expiry_date:%d %b})")
    if listing.pickups.filter(ngo=ngo, status__in=["requested", "confirmed", "in_transit"]).exists():
        raise ValueError(f"{ngo.name} already has an open pickup for this listing")
    match = Match.objects.filter(listing=listing, ngo=ngo).first()
    pickup = Pickup.objects.create(
        listing=listing, ngo=ngo, match=match, quantity_kg=quantity_kg, scheduled_start=start,
        scheduled_end=end, initiated_by=initiated_by,
        ngo_confirmed_at=now if initiated_by == "ngo" else None,
        donor_confirmed_at=now if initiated_by == "donor" else None,
        **{k: v for k, v in extra.items() if k in ("driver_name", "driver_phone", "vehicle", "notes")})
    if match:
        match.status = Match.Status.REQUESTED
        match.save(update_fields=["status"])
    listing.refresh_status()
    when = timezone.localtime(start).strftime("%a %d %b, %H:%M")
    if initiated_by == "ngo":
        notify(listing.donor, f"Pickup requested: {listing.title}",
               f"{ngo.name} wants to collect {quantity_kg:g} kg on {when}. Confirm to schedule it.",
               kind=KIND.PICKUP, link=f"/pickups/{pickup.id}")
    else:
        notify(ngo, f"Donation offered: {listing.title}",
               f"{listing.donor.name} offered {quantity_kg:g} kg for pickup on {when}. Confirm to accept.",
               kind=KIND.PICKUP, link=f"/pickups/{pickup.id}")
    return pickup


def _other(pickup, side):
    return pickup.ngo if side == "donor" else pickup.listing.donor


def confirm(pickup, side):
    now = timezone.now()
    if pickup.status != Pickup.Status.REQUESTED:
        raise ValueError(f"Pickup is already {pickup.get_status_display().lower()}")
    if (side == "donor" and pickup.donor_confirmed_at) or (side == "ngo" and pickup.ngo_confirmed_at):
        raise ValueError("You have already confirmed - waiting for the other side")
    if side == "donor":
        pickup.donor_confirmed_at = now
    else:
        pickup.ngo_confirmed_at = now
    if pickup.donor_confirmed_at and pickup.ngo_confirmed_at:
        pickup.status = Pickup.Status.CONFIRMED
    pickup.save()
    when = timezone.localtime(pickup.scheduled_start).strftime("%a %d %b, %H:%M")
    title = "Pickup confirmed" if pickup.status == Pickup.Status.CONFIRMED else "Pickup acknowledged"
    for org in (pickup.ngo, pickup.listing.donor):
        notify(org, f"{title}: {pickup.listing.title}",
               f"{pickup.quantity_kg:g} kg · {when} · {pickup.listing.pickup_address}",
               kind=KIND.PICKUP, link=f"/pickups/{pickup.id}")
    return pickup


def reschedule(pickup, side, start, end):
    if pickup.status not in (Pickup.Status.REQUESTED, Pickup.Status.CONFIRMED):
        raise ValueError("Only upcoming pickups can be rescheduled")
    if end <= start:
        raise ValueError("Pickup end must be after start")
    if end < timezone.now():
        raise ValueError("That time is already over - choose a future time")
    if timezone.localtime(start).date() > pickup.listing.expiry_date:
        raise ValueError("Pickup must happen on or before the best-before date")
    pickup.scheduled_start, pickup.scheduled_end = start, end
    pickup.status = Pickup.Status.REQUESTED
    pickup.reminder_sent = False
    now = timezone.now()
    pickup.donor_confirmed_at = now if side == "donor" else None
    pickup.ngo_confirmed_at = now if side == "ngo" else None
    pickup.save()
    when = timezone.localtime(start).strftime("%a %d %b, %H:%M")
    notify(_other(pickup, side), f"New pickup time proposed: {pickup.listing.title}",
           f"Proposed for {when}. Confirm to keep the pickup.", kind=KIND.PICKUP, link=f"/pickups/{pickup.id}")
    return pickup


@transaction.atomic
def mark_collected(pickup, **extra):
    if pickup.status != Pickup.Status.CONFIRMED:
        raise ValueError("Only scheduled pickups can be marked as collected")
    pickup.status = Pickup.Status.IN_TRANSIT
    pickup.picked_up_at = timezone.now()
    for k in ("driver_name", "driver_phone", "vehicle"):
        if extra.get(k):
            setattr(pickup, k, extra[k])
    pickup.save()
    listing = pickup.listing
    if listing.batch_id and listing.batch.quantity > 0:
        batch = listing.batch
        units = pickup.quantity_kg / (batch.product.unit_weight_kg or 1)
        consume_stock(batch.product, min(units, batch.quantity), StockTransaction.Type.DONATION, batch=batch,
                      source=StockTransaction.Source.SYSTEM, reference=f"PICKUP-{pickup.id}",
                      note=f"Donated to {pickup.ngo.name}")
    notify(listing.donor, f"Collected: {listing.title}", f"{pickup.ngo.name} collected {pickup.quantity_kg:g} kg.",
           kind=KIND.PICKUP, link=f"/pickups/{pickup.id}")
    return pickup


def complete(pickup, *, quantity_received_kg=None, meals_served=None, beneficiaries_served=None, notes=""):
    if pickup.status not in (Pickup.Status.IN_TRANSIT, Pickup.Status.CONFIRMED):
        raise ValueError("Pickup must be scheduled or in transit to complete")
    from django.conf import settings
    kg = quantity_received_kg if quantity_received_kg is not None else pickup.quantity_kg
    if kg > pickup.quantity_kg * 1.1 + 0.01:
        raise ValueError(f"Received quantity cannot exceed the {pickup.quantity_kg:g} kg that was collected")
    if pickup.status == Pickup.Status.CONFIRMED:
        mark_collected(pickup)
    pickup.status = Pickup.Status.COMPLETED
    pickup.delivered_at = timezone.now()
    pickup.quantity_received_kg = kg
    pickup.meals_served = meals_served if meals_served is not None else int(kg / settings.IMPACT["KG_PER_MEAL"])
    pickup.beneficiaries_served = beneficiaries_served
    if notes:
        pickup.notes = (pickup.notes + "\n" + notes).strip()
    pickup.save()
    pickup.listing.refresh_status()
    update_reliability(pickup.ngo)
    notify(pickup.listing.donor, f"Delivered: {pickup.listing.title}",
           f"{pickup.ngo.name} received {kg:g} kg — about {pickup.meals_served} meals.",
           kind=KIND.PICKUP, link=f"/pickups/{pickup.id}")
    return pickup


def cancel(pickup, side, reason="", no_show=False):
    if pickup.status in (Pickup.Status.COMPLETED, Pickup.Status.CANCELLED, Pickup.Status.NO_SHOW):
        raise ValueError("Pickup is already closed")
    pickup.status = Pickup.Status.NO_SHOW if no_show else Pickup.Status.CANCELLED
    pickup.cancel_reason = reason
    pickup.save()
    pickup.listing.refresh_status()
    if no_show:
        update_reliability(pickup.ngo)
    notify(_other(pickup, side), f"Pickup {'marked no-show' if no_show else 'cancelled'}: {pickup.listing.title}",
           reason or "", kind=KIND.PICKUP, link=f"/pickups/{pickup.id}")
    return pickup


def send_reminders():
    soon = timezone.now() + timedelta(hours=2)
    qs = Pickup.objects.filter(status=Pickup.Status.CONFIRMED, reminder_sent=False,
                               scheduled_start__lte=soon, scheduled_start__gte=timezone.now())
    n = 0
    for p in qs.select_related("listing__donor", "ngo"):
        when = timezone.localtime(p.scheduled_start).strftime("%H:%M")
        for org in (p.ngo, p.listing.donor):
            notify(org, f"Pickup at {when}: {p.listing.title}", p.listing.pickup_address,
                   kind=KIND.PICKUP, link=f"/pickups/{p.id}")
        p.reminder_sent = True
        p.save(update_fields=["reminder_sent"])
        n += 1
    return n


def expire_listings():
    n = 0
    for l in SurplusListing.objects.filter(status=SurplusListing.Status.AVAILABLE):
        before = l.status
        l.refresh_status()
        n += l.status != before
    return n
