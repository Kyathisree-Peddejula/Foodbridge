"""
Import FreshRetailNet-50K (https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K)
into FoodBridge as business tenants with products, daily sales history and current stock.

    python manage.py import_freshretail --stores 5 --products 30
    python manage.py import_freshretail --from-hf           # download directly

Dataset dates (2024) are shifted so the last day of data becomes "yesterday".
"""
import random
from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Organization, User
from inventory.models import FoodCategory, InventoryBatch, Product, StockTransaction
from inventory.services import run_expiry_scan
from inventory.taxonomy import ensure_taxonomy, fr_category_slug

NAMES = {
    "vegetables": ["Tomato", "Spinach bunch", "Cucumber", "Broccoli", "Carrot", "Bell pepper", "Lettuce",
                   "Okra", "Cauliflower", "Green beans", "Mushroom tray", "Coriander bunch"],
    "fruits": ["Banana", "Apple", "Mango", "Papaya", "Grapes", "Strawberry box", "Watermelon", "Guava",
               "Pomegranate", "Orange", "Kiwi pack", "Pineapple"],
    "meat-seafood": ["Chicken breast", "Chicken curry cut", "Mutton", "Rohu fish", "Prawns", "Minced meat",
                     "Salmon fillet", "Pork belly"],
    "dairy": ["Toned milk 1L", "Curd 500g", "Paneer 200g", "Cheese slices", "Butter 100g", "Greek yogurt",
              "Fresh cream", "Eggs (12)"],
    "bakery": ["Whole wheat bread", "Multigrain loaf", "Croissant", "Pav buns", "Brown bread", "Muffin pack",
               "Garlic bread", "Burger buns"],
    "prepared-deli": ["Veg sandwich", "Chicken wrap", "Garden salad", "Idli batter", "Paneer tikka roll",
                      "Pasta salad", "Sushi box", "Dosa batter"],
    "frozen": ["Frozen peas", "Frozen corn", "Chicken nuggets", "Frozen paratha", "French fries",
               "Frozen mixed veg"],
    "sweets": ["Gulab jamun", "Rasgulla", "Kaju barfi", "Chocolate pastry", "Kheer cup", "Fruit custard"],
}
COST = {"vegetables": 40, "fruits": 90, "meat-seafood": 320, "dairy": 60, "bakery": 45, "prepared-deli": 110,
        "frozen": 150, "sweets": 200}


def load_frame(from_hf, path):
    if from_hf:
        try:
            from datasets import load_dataset
        except ImportError as exc:
            raise CommandError("pip install datasets") from exc
        return load_dataset("Dingdong-Inc/FreshRetailNet-50K", split="train").to_pandas()
    path = path or settings.DATASET_DIR / "train.parquet"
    if not path.exists():
        raise CommandError(f"{path} not found. Run: python scripts/fetch_dataset.py  (or --synthetic)")
    return pd.read_parquet(path)


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, p):
        p.add_argument("--from-hf", action="store_true")
        p.add_argument("--path", type=str)
        p.add_argument("--stores", type=int, default=4)
        p.add_argument("--products", type=int, default=25, help="products per store (top sellers)")
        p.add_argument("--days", type=int, default=60, help="days of sales history to import")
        p.add_argument("--scale", type=float, default=8.0,
                       help="sale_amount is normalised in the dataset; units = sale_amount * scale")
        p.add_argument("--center", type=str, default="12.9716,77.5946", help="lat,lng to place stores around")
        p.add_argument("--password", type=str, default="Demo@12345")
        p.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **o):
        from pathlib import Path
        rng = random.Random(o["seed"])
        ensure_taxonomy()
        cats = {c.slug: c for c in FoodCategory.objects.all()}
        df = load_frame(o["from_hf"], Path(o["path"]) if o["path"] else None)
        cols = ["city_id", "store_id", "first_category_id", "second_category_id", "third_category_id",
                "product_id", "dt", "sale_amount", "stock_hour6_22_cnt", "discount", "holiday_flag", "activity_flag"]
        df = df[cols].copy()
        df["dt"] = pd.to_datetime(df["dt"])
        last = df["dt"].max()
        shift = (timezone.localdate() - timedelta(days=1)) - last.date()
        df = df[df["dt"] > last - pd.Timedelta(days=o["days"])]
        stores = df.groupby("store_id")["sale_amount"].sum().nlargest(o["stores"]).index.tolist()
        lat0, lng0 = map(float, o["center"].split(","))
        tz = timezone.get_current_timezone()
        summary = []
        for s_idx, store_id in enumerate(stores):
            sdf = df[df["store_id"] == store_id]
            city_id = int(sdf["city_id"].iloc[0])
            top = sdf.groupby("product_id")["sale_amount"].sum().nlargest(o["products"]).index.tolist()
            with transaction.atomic():
                org, _ = Organization.objects.update_or_create(
                    fr_store_id=int(store_id), org_type="business",
                    defaults=dict(name=f"FreshMart Store {int(store_id)}", kind="supermarket", fr_city_id=city_id,
                                  city="Bengaluru", address=f"Store {int(store_id)}, Retail Park, Bengaluru",
                                  latitude=round(lat0 + rng.uniform(-0.08, 0.08), 6),
                                  longitude=round(lng0 + rng.uniform(-0.08, 0.08), 6),
                                  storage_capacity_kg=4000, is_verified=True))
                email = f"store{int(store_id)}@foodbridge.dev"
                if not User.objects.filter(email=email).exists():
                    User.objects.create_user(username=email, email=email, password=o["password"],
                                             first_name="Store", last_name=str(int(store_id)),
                                             role="business", organization=org)
                StockTransaction.objects.filter(organization=org, source="import").delete()
                txns, n_batches = [], 0
                for pid in top:
                    pdf = sdf[sdf["product_id"] == pid].sort_values("dt")
                    r0 = pdf.iloc[0]
                    slug = fr_category_slug(r0["first_category_id"])
                    cat = cats[slug]
                    names = NAMES[slug]
                    name = f"{names[int(pid) % len(names)]} · FR{int(pid)}"
                    cost = round(COST[slug] * rng.uniform(0.7, 1.4), 2)
                    product, _ = Product.objects.update_or_create(
                        organization=org, sku=f"FR-{int(pid)}",
                        defaults=dict(name=name, category=cat, unit="kg", unit_weight_kg=1.0, unit_cost=cost,
                                      barcode=f"69{int(store_id):04d}{int(pid):06d}",
                                      fr_product_id=int(pid), fr_first_category_id=int(r0["first_category_id"]),
                                      fr_second_category_id=int(r0["second_category_id"]),
                                      fr_third_category_id=int(r0["third_category_id"])))
                    for r in pdf.itertuples(index=False):
                        qty = round(float(r.sale_amount) * o["scale"], 3)
                        if qty <= 0:
                            continue
                        day = r.dt.date() + shift
                        txns.append(StockTransaction(
                            organization=org, product=product, txn_type="sale", quantity=qty,
                            unit_price=round(cost * 1.3 * float(r.discount), 2),
                            occurred_at=datetime.combine(day, time(18, 0), tz), source="import",
                            reference=f"FR-{int(store_id)}-{int(pid)}-{r.dt.date()}", discount=float(r.discount),
                            holiday_flag=bool(r.holiday_flag), activity_flag=bool(r.activity_flag),
                            stockout_hours=int(r.stock_hour6_22_cnt)))
                    # current stock: a couple of batches sized around recent demand
                    InventoryBatch.objects.filter(product=product).delete()
                    daily = max(0.5, float(pdf["sale_amount"].tail(14).mean()) * o["scale"])
                    for _ in range(rng.choice([1, 1, 2])):
                        life = cat.default_shelf_life_days
                        days_left = rng.randint(-1, max(1, life))
                        qty = round(daily * rng.uniform(0.8, 4.5), 1)
                        InventoryBatch.objects.create(
                            organization=org, product=product, quantity=qty,
                            received_date=timezone.localdate() - timedelta(days=max(0, life - days_left)),
                            expiry_date=timezone.localdate() + timedelta(days=days_left),
                            storage_location=rng.choice(["Chiller 1", "Chiller 2", "Aisle 3", "Back store"]))
                        n_batches += 1
                StockTransaction.objects.bulk_create(txns, batch_size=2000)
            summary.append(f"store {int(store_id)}: {len(top)} products, {len(txns)} sales rows, {n_batches} batches")
        run_expiry_scan()
        for line in summary:
            self.stdout.write(self.style.SUCCESS(line))
