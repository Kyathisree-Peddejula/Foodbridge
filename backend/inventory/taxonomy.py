"""Built-in food taxonomy + keyword classifier + FreshRetailNet category mapping."""
import re

TAXONOMY = [
    # slug, name, perishability, storage, temp, shelf_life, warn, crit, co2e/kg, color, keywords, notes
    ("cooked-meals", "Cooked meals", "high", "hot_hold", ">63 °C or <5 °C", 1, 1, 0, 3.0, "#E8742C",
     "cooked,biryani,curry,thali,meal,gravy,sabzi,fried rice,pulao,khichdi,pasta bake,lasagna,soup,stew,dal tadka",
     "Serve or chill within 2 hours of cooking"),
    ("prepared-deli", "Ready-to-eat & deli", "high", "chilled", "0-5 °C", 2, 1, 0, 2.8, "#C2567A",
     "sandwich,salad,wrap,deli,ready to eat,samosa,idli,dosa,momo,burger,pizza,sushi,roll",
     "Keep chilled; discard if left out >2 h"),
    ("bakery", "Bread & bakery", "high", "ambient", "15-25 °C", 3, 2, 1, 1.6, "#E0B02C",
     "bread,bun,cake,pastry,croissant,muffin,bagel,cookie,pav,loaf,donut,baguette,brownie,bakery",
     "Store dry; day-old bread is ideal for donation"),
    ("fruits", "Fresh fruits", "high", "ambient", "8-15 °C", 5, 2, 1, 1.1, "#1FA463",
     "apple,banana,mango,orange,grape,berry,berries,papaya,melon,watermelon,fruit,pear,guava,pineapple,kiwi,pomegranate",
     "Separate ethylene producers (banana, apple)"),
    ("vegetables", "Fresh vegetables", "high", "chilled", "2-8 °C", 5, 2, 1, 1.0, "#4C9A2A",
     "tomato,onion,potato,spinach,lettuce,cabbage,carrot,cauliflower,vegetable,veg,beans,peas,capsicum,cucumber,greens,brinjal,okra,broccoli,mushroom",
     "Leafy greens are the most perishable"),
    ("dairy", "Dairy & eggs", "high", "chilled", "0-4 °C", 7, 3, 1, 3.2, "#3AAFD9",
     "milk,curd,yogurt,yoghurt,paneer,cheese,butter,cream,egg,eggs,lassi,dahi,buttermilk,tofu",
     "Cold chain must be maintained during pickup"),
    ("meat-seafood", "Meat & seafood", "high", "chilled", "0-3 °C", 3, 2, 1, 12.0, "#C0392B",
     "chicken,mutton,fish,prawn,shrimp,meat,beef,pork,seafood,lamb,sausage,bacon,ham,salami",
     "Only donate with an insulated vehicle"),
    ("sweets", "Sweets & desserts", "medium", "chilled", "2-8 °C", 4, 2, 1, 2.2, "#B460C9",
     "sweet,mithai,laddu,halwa,dessert,gulab jamun,barfi,kheer,pudding,rasgulla,jalebi,ice cream",
     ""),
    ("beverages", "Beverages", "medium", "chilled", "2-8 °C", 30, 7, 3, 0.9, "#2F80ED",
     "juice,soda,drink,water,tea,coffee,smoothie,beverage,milkshake,coconut water", ""),
    ("frozen", "Frozen foods", "low", "frozen", "-18 °C", 90, 14, 5, 2.5, "#5B6CFF",
     "frozen,nuggets,frozen peas,frozen corn,fries", "Do not refreeze once thawed"),
    ("packaged", "Packaged & dry goods", "low", "ambient", "<25 °C", 120, 21, 7, 1.8, "#6C63FF",
     "biscuit,chips,snack,cereal,instant noodles,packet,sauce,ketchup,jam,canned,tinned,namkeen,spread,chocolate",
     ""),
    ("grains", "Grains & pulses", "low", "ambient", "<25 °C", 180, 30, 10, 1.4, "#A0522D",
     "rice,wheat,atta,flour,lentil,dal,oats,grain,pulse,millet,rava,sooji,poha,quinoa,chana,rajma",
     "Keep sealed and away from moisture"),
]

# FreshRetailNet-50K is a fresh-retail dataset with anonymized category ids.
# We map first_category_id onto the fresh part of our taxonomy deterministically.
FRESH_SLUGS = ["vegetables", "fruits", "meat-seafood", "dairy", "bakery", "prepared-deli", "frozen", "sweets"]


def fr_category_slug(first_category_id):
    return FRESH_SLUGS[int(first_category_id) % len(FRESH_SLUGS)]


def ensure_taxonomy():
    from inventory.models import FoodCategory
    for (slug, name, per, storage, temp, life, warn, crit, co2, color, kw, notes) in TAXONOMY:
        FoodCategory.objects.update_or_create(slug=slug, defaults=dict(
            name=name, perishability=per, storage=storage, storage_temp_c=temp,
            default_shelf_life_days=life, warning_days=warn, critical_days=crit,
            co2e_per_kg=co2, color=color, keywords=kw, handling_notes=notes))


def classify(text):
    """Keyword classifier. Returns (FoodCategory|None, confidence 0-1, matched keywords)."""
    from inventory.models import FoodCategory
    t = " " + re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()) + " "
    best, best_score, best_hits = None, 0.0, []
    for cat in FoodCategory.objects.all():
        hits = [k for k in cat.keyword_list() if f" {k} " in t or f" {k}s " in t]
        if not hits:
            continue
        # longer / multi-word keywords are more specific
        score = sum(1 + 0.5 * (len(k.split()) - 1) + len(k) / 20 for k in hits)
        if score > best_score:
            best, best_score, best_hits = cat, score, hits
    conf = min(0.99, 0.45 + 0.2 * best_score) if best else 0.0
    return best, round(conf, 2), best_hits
