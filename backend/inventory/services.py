"""Inventory domain logic: stock movements (FIFO), expiry engine, CSV import, scanning."""
import csv
import io
import logging
from datetime import date, datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.models import Notification
from core.services import notify
from inventory.models import (BulkUpload, ExpiryAlert, ExpiryThreshold, FoodCategory, InventoryBatch, Product,
                              StockTransaction)
from inventory.taxonomy import classify

log = logging.getLogger(__name__)
T = StockTransaction.Type


# ------------------------------------------------------------------ products & stock
def get_or_create_product(org, *, name=None, sku=None, barcode=None, category=None, unit=None,
                          unit_cost=None, unit_weight_kg=None):
    q = Q()
    if sku:
        q |= Q(sku__iexact=sku)
    if barcode:
        q |= Q(barcode=barcode)
    product = Product.objects.filter(q, organization=org).first() if q else None
    if product is None and name:
        product = Product.objects.filter(organization=org, name__iexact=name).first()
    if product:
        # upsert: explicit master data from the latest upload / scan wins over earlier defaults
        changed = []
        if unit and unit != product.unit:
            product.unit = unit; changed.append("unit")  # noqa: E702
        if unit_weight_kg and unit_weight_kg != product.unit_weight_kg:
            product.unit_weight_kg = float(unit_weight_kg); changed.append("unit_weight_kg")  # noqa: E702
        if unit_cost not in (None, "") and float(unit_cost) != float(product.unit_cost or 0):
            product.unit_cost = unit_cost; changed.append("unit_cost")  # noqa: E702
        if barcode and not product.barcode:
            product.barcode = barcode; changed.append("barcode")  # noqa: E702
        if isinstance(category, str) and category:
            cat = FoodCategory.objects.filter(Q(slug__iexact=category) | Q(name__iexact=category)).first()
            if cat and cat.id != product.category_id:
                product.category = cat; changed.append("category")  # noqa: E702
        if changed:
            product.save(update_fields=changed)
        return product, False
    if not name:
        raise ValueError("Unknown product: provide a name to create it")
    cat = category
    if isinstance(category, str) and category:
        cat = FoodCategory.objects.filter(Q(slug__iexact=category) | Q(name__iexact=category)).first()
    if not cat:
        cat, _, _ = classify(name)
    try:
        with transaction.atomic():
            product = Product.objects.create(
                organization=org, name=name, sku=sku or _auto_sku(org, name), barcode=barcode or "",
                category=cat, unit=unit or Product.Unit.KG, unit_cost=unit_cost or 0,
                unit_weight_kg=unit_weight_kg or 1.0)
    except IntegrityError:  # concurrent scan / upload created it first → use that one
        existing = Product.objects.filter(q, organization=org).first() if q else None
        if existing is None:
            raise
        return existing, False
    return product, True


def _auto_sku(org, name):
    base = "".join(ch for ch in name.upper() if ch.isalnum())[:6] or "ITEM"
    n = Product.objects.filter(organization=org).count() + 1
    sku = f"{base}-{n:04d}"
    while Product.objects.filter(organization=org, sku=sku).exists():
        n += 1
        sku = f"{base}-{n:04d}"
    return sku


@transaction.atomic
def receive_stock(product, quantity, *, expiry_date=None, received_date=None, unit_cost=None,
                  location="", source=StockTransaction.Source.MANUAL, reference="", user=None, occurred_at=None):
    received_date = received_date or timezone.localdate()
    expiry_date = expiry_date or (received_date + timedelta(days=product.effective_shelf_life))
    batch = InventoryBatch.objects.create(
        organization=product.organization, product=product, quantity=float(quantity),
        received_date=received_date, expiry_date=expiry_date, storage_location=location)
    StockTransaction.objects.create(
        organization=product.organization, product=product, batch=batch, txn_type=T.PURCHASE,
        quantity=float(quantity), unit_price=unit_cost if unit_cost is not None else product.unit_cost,
        occurred_at=occurred_at or timezone.now(), source=source, reference=reference, created_by=user)
    refresh_batch_status(batch)
    return batch


@transaction.atomic
def consume_stock(product, quantity, txn_type=T.SALE, *, unit_price=0, source=StockTransaction.Source.MANUAL,
                  reference="", user=None, occurred_at=None, batch=None, note=""):
    """Remove stock first-expired-first-out. Returns (transactions, unfulfilled_qty)."""
    remaining = float(quantity)
    batches = [batch] if batch else list(
        InventoryBatch.objects.select_for_update().filter(product=product, quantity__gt=0)
        .exclude(status=InventoryBatch.Status.DEPLETED).order_by("expiry_date", "id"))
    txns = []
    for b in batches:
        if remaining <= 1e-9:
            break
        take = min(b.quantity, remaining)
        b.quantity = round(b.quantity - take, 4)
        remaining = round(remaining - take, 4)
        if b.quantity <= 1e-9:
            b.quantity = 0
            b.status = InventoryBatch.Status.DEPLETED
        b.save(update_fields=["quantity", "status"])
        txns.append(StockTransaction.objects.create(
            organization=product.organization, product=product, batch=b, txn_type=txn_type, quantity=take,
            unit_price=unit_price, occurred_at=occurred_at or timezone.now(), source=source,
            reference=reference, created_by=user, note=note))
    if remaining > 1e-9 and txn_type == T.SALE:
        # record the sale even without matching stock so demand history stays complete
        txns.append(StockTransaction.objects.create(
            organization=product.organization, product=product, txn_type=txn_type, quantity=remaining,
            unit_price=unit_price, occurred_at=occurred_at or timezone.now(), source=source,
            reference=reference, created_by=user, note="no stock on hand"))
        remaining = 0
    return txns, remaining


# ------------------------------------------------------------------ expiry engine
def thresholds_for(org, category):
    """Resolve (warning_days, critical_days): org+category > org default > taxonomy."""
    rules = {(r.category_id): r for r in ExpiryThreshold.objects.filter(organization=org)}
    r = rules.get(category.id if category else None) or rules.get(None)
    if r:
        return r.warning_days, r.critical_days
    if category:
        return category.warning_days, category.critical_days
    return 3, 1


def refresh_batch_status(batch, thresholds=None):
    if batch.quantity <= 0:
        new = InventoryBatch.Status.DEPLETED
    elif batch.status == InventoryBatch.Status.LISTED and batch.days_to_expiry >= 0:
        return batch.status
    else:
        warn, _ = thresholds or thresholds_for(batch.organization, batch.product.category)
        d = batch.days_to_expiry
        new = (InventoryBatch.Status.EXPIRED if d < 0 else
               InventoryBatch.Status.EXPIRING if d <= warn else InventoryBatch.Status.ACTIVE)
    if new != batch.status:
        batch.status = new
        batch.save(update_fields=["status"])
    return new


def run_expiry_scan(organization=None):
    """Update batch statuses and raise alerts for items near/after expiry. Idempotent."""
    qs = InventoryBatch.objects.select_related("product__category", "organization").filter(quantity__gt=0)
    if organization:
        qs = qs.filter(organization=organization)
    created = 0
    per_org = {}
    cache = {}
    for b in qs:
        key = (b.organization_id, b.product.category_id)
        if key not in cache:
            cache[key] = thresholds_for(b.organization, b.product.category)
        warn, crit = cache[key]
        refresh_batch_status(b, (warn, crit))
        d = b.days_to_expiry
        level = (ExpiryAlert.Level.EXPIRED if d < 0 else ExpiryAlert.Level.CRITICAL if d <= crit
                 else ExpiryAlert.Level.WARNING if d <= warn else None)
        if not level:
            continue
        when = "expired" if d < 0 else "expires today" if d == 0 else f"expires in {d} day{'s' if d != 1 else ''}"
        msg = f"{b.product.name} ({b.quantity:g} {b.product.unit}, batch {b.batch_code}) {when}"
        _, was_new = ExpiryAlert.objects.get_or_create(
            batch=b, level=level, defaults=dict(organization=b.organization, days_left=d, message=msg))
        if was_new:
            created += 1
            per_org.setdefault(b.organization, []).append((level, msg))
    for org, items in per_org.items():
        crit_n = sum(1 for lvl, _ in items if lvl != ExpiryAlert.Level.WARNING)
        title = f"{len(items)} item(s) need attention" + (f" · {crit_n} critical" if crit_n else "")
        notify(org, title, "\n".join(m for _, m in items[:20]), kind=Notification.Kind.EXPIRY, link="/alerts")
    return {"batches_checked": qs.count(), "alerts_created": created}


# ------------------------------------------------------------------ CSV bulk upload
INVENTORY_COLUMNS = ["name", "sku", "barcode", "category", "quantity", "unit", "unit_cost",
                     "unit_weight_kg", "received_date", "expiry_date", "storage_location"]
TRANSACTION_COLUMNS = ["sku", "name", "type", "quantity", "unit_price", "occurred_at", "reference",
                       "discount", "holiday_flag", "activity_flag"]
ALIASES = {"product": "name", "product_name": "name", "item": "name", "qty": "quantity", "cost": "unit_cost",
           "price": "unit_price", "expiry": "expiry_date", "best_before": "expiry_date", "exp_date": "expiry_date",
           "received": "received_date", "location": "storage_location", "date": "occurred_at",
           "dt": "occurred_at", "txn_type": "type", "sale_amount": "quantity", "ean": "barcode", "upc": "barcode"}


def csv_template(mode="inventory"):
    cols = INVENTORY_COLUMNS if mode == "inventory" else TRANSACTION_COLUMNS
    sample = ([["Whole wheat bread", "BRD-001", "8901234567890", "bakery", "40", "pcs", "35", "0.4",
                timezone.localdate().isoformat(), (timezone.localdate() + timedelta(days=3)).isoformat(), "Shelf A"],
               ["Paneer 200g", "DRY-014", "8900000000014", "", "25", "pack", "90", "0.2", "", "", "Chiller 2"]]
              if mode == "inventory" else
              [["BRD-001", "", "sale", "12", "40", (timezone.now() - timedelta(days=1)).isoformat(), "INV-1001",
                "1.0", "0", "0"]])
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(cols)
    w.writerows(sample)
    return out.getvalue()


def _norm_row(row):
    clean = {}
    for k, v in row.items():
        if k is None:
            continue
        key = k.strip().lower().replace(" ", "_")
        clean[ALIASES.get(key, key)] = (v or "").strip()
    return clean


def _date(v):
    if not v:
        return None
    d = parse_date(v)
    if d:
        return d
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unrecognised date '{v}'")


def _dt(v):
    if not v:
        return timezone.now()
    d = parse_datetime(v)
    if d is None:
        d = datetime.combine(_date(v), datetime.min.time())
    return d if timezone.is_aware(d) else timezone.make_aware(d)


def import_csv(org, fileobj, *, mode="inventory", user=None, file_name="upload.csv"):
    raw = fileobj.read()
    if isinstance(raw, bytes):
        for enc in ("utf-8-sig", "cp1252", "latin-1"):  # Excel on Windows saves cp1252
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    else:
        text = raw
    try:  # Excel in many locales writes ';' separated files
        dialect = csv.Sniffer().sniff(text.split("\n", 1)[0], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    log_row = BulkUpload.objects.create(organization=org, file_name=file_name, mode=mode, created_by=user)
    errors, created, total = [], 0, 0
    for i, row in enumerate(reader, start=2):
        total += 1
        r = _norm_row(row)
        try:
            with transaction.atomic():
                if mode == "inventory":
                    qty = float(r.get("quantity") or 0)
                    if qty <= 0:
                        raise ValueError("quantity must be > 0")
                    product, _ = get_or_create_product(
                        org, name=r.get("name"), sku=r.get("sku"), barcode=r.get("barcode"),
                        category=r.get("category"), unit=r.get("unit") or None,
                        unit_cost=r.get("unit_cost") or None, unit_weight_kg=float(r["unit_weight_kg"])
                        if r.get("unit_weight_kg") else None)
                    exp, rec = _date(r.get("expiry_date")), _date(r.get("received_date"))
                    if exp and rec and exp < rec:
                        raise ValueError("expiry_date is before received_date")
                    receive_stock(product, qty, expiry_date=exp,
                                  received_date=rec, unit_cost=r.get("unit_cost") or None,
                                  location=r.get("storage_location", ""), source=StockTransaction.Source.CSV, user=user)
                else:
                    product, _ = get_or_create_product(org, name=r.get("name"), sku=r.get("sku"))
                    ttype = (r.get("type") or "sale").lower()
                    if ttype not in T.values:
                        raise ValueError(f"type must be one of {', '.join(T.values)}")
                    qty = float(r.get("quantity") or 0)
                    if qty <= 0:
                        raise ValueError("quantity must be > 0")
                    common = dict(organization=org, product=product, txn_type=ttype, quantity=qty,
                                  unit_price=r.get("unit_price") or 0, occurred_at=_dt(r.get("occurred_at")),
                                  source=StockTransaction.Source.CSV, reference=r.get("reference", ""),
                                  discount=float(r["discount"]) if r.get("discount") else None,
                                  holiday_flag=r.get("holiday_flag") in {"1", "true", "True"},
                                  activity_flag=r.get("activity_flag") in {"1", "true", "True"}, created_by=user)
                    StockTransaction.objects.create(**common)
                created += 1
        except Exception as exc:  # collect row errors, keep going
            errors.append({"row": i, "error": str(exc)})
    log_row.rows_total, log_row.rows_created, log_row.rows_failed = total, created, len(errors)
    log_row.errors = errors[:200]
    log_row.save()
    if mode == "inventory":
        run_expiry_scan(org)
    return log_row


# ------------------------------------------------------------------ barcode scanning
def apply_scan(org, *, barcode, action, quantity=1, expiry_date=None, name=None, category=None, user=None):
    product = Product.objects.filter(organization=org, barcode=barcode).first()
    if product is None:
        if action != "receive" or not name:
            raise ValueError("Barcode not found. Scan with action=receive and a product name to create it.")
        product, _ = get_or_create_product(org, name=name, barcode=barcode, category=category)
    src = StockTransaction.Source.SCAN
    if action == "receive":
        batch = receive_stock(product, quantity, expiry_date=expiry_date, source=src, user=user)
        return product, {"batch_id": batch.id, "message": f"Added {quantity:g} {product.unit} of {product.name}"}
    ttype = {"sell": T.SALE, "waste": T.WASTE, "remove": T.ADJUSTMENT}.get(action)
    if not ttype:
        raise ValueError("action must be receive, sell, waste or remove")
    _, short = consume_stock(product, quantity, ttype, source=src, user=user)
    msg = f"Removed {quantity - short:g} {product.unit} of {product.name}"
    if short:
        msg += f" ({short:g} more than on hand)"
    return product, {"message": msg}
