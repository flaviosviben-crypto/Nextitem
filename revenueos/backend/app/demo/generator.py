"""Realistic demo boutique data with *correlated* behaviour.

Random data would make the product look intelligent while proving nothing. This
generator instead simulates a boutique: customers are drawn from behavioural
personas (a brand devotee, a dormant VIP, a markdown hunter, a lapsed
one-timer), and every transaction is generated from that persona's own
preferences — brand, category, palette, price ceiling, purchase rhythm and
discount appetite.

The analytics then *discover* those patterns from the transaction ledger, which
is the point: the demo demonstrates the engine, it does not fake it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

SEED = 20260318

FIRST_NAMES_F = ["Giulia", "Sofia", "Chiara", "Francesca", "Alessia", "Martina", "Elena",
                 "Valentina", "Beatrice", "Camilla", "Federica", "Ludovica", "Silvia",
                 "Anna", "Marta", "Caterina", "Benedetta", "Irene", "Serena", "Alice",
                 "Claudia", "Eleonora", "Gaia", "Ilaria", "Laura", "Michela", "Nicole",
                 "Paola", "Rebecca", "Sara", "Veronica", "Bianca", "Cecilia", "Emma"]
FIRST_NAMES_M = ["Marco", "Luca", "Andrea", "Matteo", "Alessandro", "Francesco", "Davide",
                 "Simone", "Riccardo", "Federico", "Lorenzo", "Giacomo", "Tommaso",
                 "Filippo", "Edoardo", "Nicolò", "Stefano", "Paolo", "Giovanni"]
LAST_NAMES = ["Rossi", "Bianchi", "Ferrari", "Romano", "Conti", "Ricci", "Marino", "Greco",
              "Bruno", "Gallo", "Costa", "Fontana", "Rizzo", "Moretti", "Barbieri",
              "Lombardi", "Colombo", "Esposito", "Villa", "Serra", "De Luca", "Mancini",
              "Longo", "Leone", "Martinelli", "Vitale", "Caruso", "Ferrara", "Galli",
              "Sartori", "Benedetti", "Pellegrini", "Grassi", "Testa", "Neri", "Rinaldi"]

CITIES = [("Milano", "Italy", 0.30), ("Roma", "Italy", 0.14), ("Firenze", "Italy", 0.10),
          ("Torino", "Italy", 0.08), ("Bologna", "Italy", 0.06), ("Verona", "Italy", 0.05),
          ("Napoli", "Italy", 0.05), ("Padova", "Italy", 0.04), ("Genova", "Italy", 0.03),
          ("Lugano", "Switzerland", 0.04), ("Paris", "France", 0.04),
          ("München", "Germany", 0.03), ("Wien", "Austria", 0.02), ("Bruxelles", "Belgium", 0.02)]

STORES = ["Milano Brera", "Milano Duomo", "Firenze Tornabuoni"]

# (brand, tier, house palette bias)
BRANDS = [
    ("Max Mara", "luxury", 1.00), ("Totême", "luxury", 1.00), ("Jil Sander", "luxury", 1.15),
    ("The Row", "ultra", 1.55), ("Loro Piana", "ultra", 1.60), ("Brunello Cucinelli", "ultra", 1.45),
    ("Acne Studios", "contemporary", 0.72), ("Ganni", "contemporary", 0.55),
    ("A.P.C.", "contemporary", 0.62), ("Isabel Marant", "contemporary", 0.80),
    ("Studio Nicholson", "contemporary", 0.85), ("Lemaire", "luxury", 1.10),
    ("Aspesi", "contemporary", 0.68), ("Herno", "luxury", 0.95), ("Nanushka", "contemporary", 0.60),
    ("Khaite", "luxury", 1.25), ("Frame", "contemporary", 0.50), ("Agolde", "contemporary", 0.45),
]

# (category, base price, repeat-purchase tendency, seasonality)
CATEGORIES = [
    ("Coats", 780, 0.25, "FW"), ("Outerwear", 640, 0.30, "FW"),
    ("Knitwear", 320, 0.75, "FW"), ("Dresses", 420, 0.45, "SS"),
    ("Shirts", 240, 0.70, "ALL"), ("Trousers", 290, 0.65, "ALL"),
    ("Skirts", 270, 0.50, "SS"), ("Bags", 690, 0.35, "ALL"),
    ("Shoes", 450, 0.45, "ALL"), ("Accessories", 160, 0.80, "ALL"),
    ("Jewellery", 280, 0.55, "ALL"), ("Denim", 230, 0.60, "ALL"),
]

COLORS = [("Black", 0.22), ("Beige", 0.13), ("Camel", 0.09), ("White", 0.10), ("Navy", 0.08),
          ("Grey", 0.08), ("Cream", 0.07), ("Brown", 0.06), ("Green", 0.05), ("Red", 0.04),
          ("Blue", 0.04), ("Pink", 0.03), ("Print", 0.01)]
NEUTRALS = {"Black", "Beige", "Camel", "White", "Navy", "Grey", "Cream", "Brown"}

CLOTHING_SIZES = ["XS", "S", "M", "L", "XL"]
SHOE_SIZES = ["36", "37", "38", "39", "40", "41"]

SEASONS = ["FW24", "SS25", "FW25", "SS26", "FW26"]


@dataclass
class Persona:
    key: str
    label: str
    weight: float
    order_span: tuple[int, int]         # lifetime orders
    cycle_days: tuple[int, int]         # typical days between orders
    basket_items: tuple[int, int]
    price_multiplier: tuple[float, float]
    discount_appetite: float            # probability a line is bought on markdown
    brand_focus: float                  # 0..1 how concentrated on one brand
    category_focus: float
    neutral_bias: float
    dormancy_days: tuple[int, int]      # days since last purchase
    tenure_days: tuple[int, int]


PERSONAS = [
    Persona("champion", "Champion", 0.10, (9, 20), (35, 60), (1, 3), (1.0, 1.5),
            0.08, 0.45, 0.5, 0.62, (5, 40), (700, 1500)),
    Persona("vip_full_price", "VIP full-price", 0.08, (6, 13), (55, 95), (1, 2), (1.3, 2.1),
            0.04, 0.55, 0.55, 0.75, (10, 70), (600, 1400)),
    Persona("brand_devotee", "Brand devotee", 0.09, (5, 12), (60, 110), (1, 2), (0.9, 1.4),
            0.14, 0.82, 0.45, 0.55, (15, 120), (500, 1300)),
    Persona("dormant_vip", "Dormant VIP", 0.07, (5, 12), (50, 90), (1, 3), (1.2, 1.9),
            0.09, 0.5, 0.5, 0.7, (190, 420), (700, 1600)),
    Persona("steady_regular", "Steady regular", 0.16, (5, 11), (70, 125), (1, 3), (0.75, 1.15),
            0.22, 0.35, 0.45, 0.5, (20, 140), (400, 1200)),
    Persona("markdown_hunter", "Markdown hunter", 0.10, (5, 13), (65, 135), (1, 3), (0.55, 0.9),
            0.78, 0.25, 0.3, 0.45, (25, 170), (400, 1300)),
    Persona("emerging", "Emerging", 0.11, (2, 5), (60, 120), (1, 3), (0.85, 1.35),
            0.15, 0.4, 0.5, 0.55, (10, 80), (100, 330)),
    Persona("new_customer", "New customer", 0.10, (1, 2), (70, 140), (1, 2), (0.7, 1.2),
            0.2, 0.3, 0.4, 0.5, (3, 60), (5, 120)),
    Persona("occasional", "Occasional", 0.11, (2, 4), (150, 260), (1, 1), (0.6, 1.0),
            0.35, 0.25, 0.3, 0.45, (60, 260), (400, 1300)),
    Persona("lapsed", "Lapsed", 0.08, (1, 4), (110, 200), (1, 2), (0.6, 1.1),
            0.3, 0.25, 0.3, 0.45, (430, 900), (600, 1700)),
]


def _weighted_choice(rng: random.Random, options: list[tuple[Any, float]]) -> Any:
    total = sum(w for _, w in options)
    pick = rng.random() * total
    upto = 0.0
    for value, weight in options:
        upto += weight
        if pick <= upto:
            return value
    return options[-1][0]


def _price_for(base: float, tier_multiplier: float, rng: random.Random) -> float:
    noise = rng.uniform(0.78, 1.34)
    raw = base * tier_multiplier * noise
    # retail price points, not random floats
    if raw < 200:
        return float(round(raw / 5) * 5 - 1)
    if raw < 600:
        return float(round(raw / 10) * 10 - 10 + 5)
    return float(round(raw / 50) * 50 - 10)


def generate_demo_dataset(
    n_customers: int = 165,
    n_products: int = 320,
    as_of: date | None = None,
    seed: int = SEED,
) -> dict[str, pd.DataFrame]:
    """Return raw-looking ``customers`` / ``transactions`` / ``inventory`` frames."""
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    today = as_of or date.today()

    products = _build_catalogue(rng, n_products, today)
    customers, transactions = _build_customers_and_sales(rng, np_rng, n_customers, products, today)

    inventory = _finalise_inventory(products, transactions, rng, today)
    return {
        "customers": customers,
        "transactions": transactions,
        "inventory": inventory,
    }


# --------------------------------------------------------------------------- #
def _build_catalogue(rng: random.Random, n_products: int, today: date) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for i in range(n_products):
        brand, tier, multiplier = rng.choice(BRANDS)
        category, base_price, repeatability, seasonality = rng.choice(CATEGORIES)
        colour = _weighted_choice(rng, COLORS)
        price = _price_for(base_price, multiplier, rng)

        if category in {"Shoes"}:
            size = rng.choice(SHOE_SIZES)
        elif category in {"Bags", "Jewellery", "Accessories"}:
            size = "Unica"
        else:
            size = rng.choice(CLOTHING_SIZES)

        # Arrival dates cluster around season deliveries; a tail of old stock
        # is deliberately left to become dead stock.
        roll = rng.random()
        if roll < 0.30:
            age_days = rng.randint(3, 55)          # fresh
        elif roll < 0.62:
            age_days = rng.randint(56, 130)
        elif roll < 0.85:
            age_days = rng.randint(131, 260)
        else:
            age_days = rng.randint(261, 620)       # ageing tail
        arrival = today - timedelta(days=age_days)

        season = SEASONS[min(len(SEASONS) - 1, max(0, 4 - age_days // 170))]
        if seasonality == "FW" and season.startswith("SS"):
            season = "FW" + season[2:]
        elif seasonality == "SS" and season.startswith("FW"):
            season = "SS" + season[2:]

        cost_ratio = {"ultra": 0.42, "luxury": 0.46, "contemporary": 0.52}[tier]
        cost = round(price * cost_ratio * rng.uniform(0.92, 1.08), 2)

        # older stock is often already marked down
        markdown = 0.0
        if age_days > 240 and rng.random() < 0.55:
            markdown = rng.choice([0.20, 0.30, 0.40])
        original_price = price
        current_price = round(price * (1 - markdown), 2) if markdown else price

        products.append({
            "product_id": f"P{1000 + i}",
            "sku": f"{brand[:3].upper()}-{category[:2].upper()}{2000 + i}-{str(size).replace(' ', '')}",
            "product_name": _product_name(rng, brand, category, colour),
            "category": category,
            "subcategory": _subcategory(rng, category),
            "brand": brand,
            "gender": "Donna" if rng.random() < 0.82 else "Uomo",
            "price": current_price,
            "original_price": original_price,
            "cost": cost,
            "size": size,
            "color": colour,
            "season": season,
            "collection": f"{season} Main",
            "arrival_date": arrival,
            "supplier": f"{brand} Italia",
            "_tier": tier,
            "_repeatability": repeatability,
            "_base_units": rng.randint(2, 7),
            "_age_days": age_days,
            "_desirability": rng.betavariate(2.2, 2.2),
        })
    return products


_NAME_PARTS = {
    "Coats": ["Wool Coat", "Belted Coat", "Double-Breasted Coat", "Teddy Coat", "Trench Coat"],
    "Outerwear": ["Quilted Jacket", "Bomber Jacket", "Padded Parka", "Field Jacket", "Blazer"],
    "Knitwear": ["Cashmere Sweater", "Ribbed Cardigan", "Merino Crewneck", "Wool Turtleneck",
                 "Fine-Knit Pullover"],
    "Dresses": ["Midi Dress", "Slip Dress", "Shirt Dress", "Knitted Dress", "Wrap Dress"],
    "Shirts": ["Poplin Shirt", "Silk Blouse", "Oversized Shirt", "Cotton Shirt"],
    "Trousers": ["Tailored Trousers", "Wide-Leg Trousers", "Pleated Trousers", "Cropped Trousers"],
    "Skirts": ["Midi Skirt", "Pleated Skirt", "Wrap Skirt", "Leather Skirt"],
    "Bags": ["Shoulder Bag", "Tote Bag", "Crossbody Bag", "Top-Handle Bag", "Weekender"],
    "Shoes": ["Leather Loafers", "Ankle Boots", "Ballet Flats", "Knee Boots", "Sling-Backs"],
    "Accessories": ["Wool Scarf", "Leather Belt", "Cashmere Gloves", "Silk Scarf", "Cap"],
    "Jewellery": ["Gold Hoops", "Chain Necklace", "Signet Ring", "Pearl Earrings"],
    "Denim": ["Straight Jeans", "Wide-Leg Jeans", "Cropped Jeans", "Denim Jacket"],
}


def _product_name(rng: random.Random, brand: str, category: str, colour: str) -> str:
    part = rng.choice(_NAME_PARTS.get(category, [category]))
    return f"{brand} {part} — {colour}"


def _subcategory(rng: random.Random, category: str) -> str:
    mapping = {
        "Coats": ["Wool", "Cashmere blend", "Technical"],
        "Outerwear": ["Casual", "Tailored", "Performance"],
        "Knitwear": ["Cashmere", "Merino", "Cotton"],
        "Dresses": ["Day", "Evening", "Knit"],
        "Bags": ["Leather", "Canvas", "Suede"],
        "Shoes": ["Leather", "Suede", "Boots"],
    }
    return rng.choice(mapping.get(category, ["Main line"]))


# --------------------------------------------------------------------------- #
def _build_customers_and_sales(rng, np_rng, n_customers, products, today):
    persona_options = [(p, p.weight) for p in PERSONAS]
    by_brand: dict[str, list[dict]] = {}
    by_category: dict[str, list[dict]] = {}
    for product in products:
        by_brand.setdefault(product["brand"], []).append(product)
        by_category.setdefault(product["category"], []).append(product)

    customers: list[dict[str, Any]] = []
    transactions: list[dict[str, Any]] = []
    tx_counter = 500000

    for i in range(n_customers):
        persona: Persona = _weighted_choice(rng, persona_options)
        gender = "F" if rng.random() < 0.79 else "M"
        first = rng.choice(FIRST_NAMES_F if gender == "F" else FIRST_NAMES_M)
        last = rng.choice(LAST_NAMES)
        city, country = _pick_city(rng)
        customer_id = f"CL{2000 + i}"

        # --- persona-specific taste --- #
        favourite_brand = rng.choice(BRANDS)[0]
        second_brand = rng.choice(BRANDS)[0]
        favourite_category = rng.choice(CATEGORIES)[0]
        second_category = rng.choice(CATEGORIES)[0]
        palette = _persona_palette(rng, persona)
        clothing_size = rng.choice(CLOTHING_SIZES)
        shoe_size = rng.choice(SHOE_SIZES)
        price_multiplier = rng.uniform(*persona.price_multiplier)

        n_orders = rng.randint(*persona.order_span)
        cycle = rng.randint(*persona.cycle_days)
        dormancy = rng.randint(*persona.dormancy_days)
        tenure = max(rng.randint(*persona.tenure_days), dormancy + cycle)

        last_purchase = today - timedelta(days=dormancy)
        order_dates: list[date] = []
        cursor = last_purchase
        for _ in range(n_orders):
            order_dates.append(cursor)
            gap = max(9, int(np_rng.normal(cycle, cycle * 0.28)))
            cursor = cursor - timedelta(days=gap)
            if (today - cursor).days > tenure:
                break
        order_dates = sorted(order_dates)

        lines_written = 0
        for order_date in order_dates:
            tx_counter += 1
            transaction_id = f"T{tx_counter}"
            store = rng.choice(STORES)
            channel = "Boutique" if rng.random() < 0.86 else "Online"
            items = rng.randint(*persona.basket_items)
            basket_ids: set[str] = set()
            for _ in range(items):
                product = _pick_product(rng, persona, by_brand, by_category, products,
                                        favourite_brand, second_brand,
                                        favourite_category, second_category,
                                        palette, clothing_size, shoe_size,
                                        price_multiplier, order_date,
                                        exclude=basket_ids)
                if product is None:
                    continue
                basket_ids.add(product["product_id"])
                discounted = rng.random() < persona.discount_appetite
                discount_pct = rng.choice([10, 15, 20, 30, 40]) if discounted else 0
                quantity = 1 if rng.random() < 0.93 else 2
                unit_price = float(product["original_price"])
                net = round(unit_price * quantity * (1 - discount_pct / 100), 2)

                transactions.append({
                    "transaction_id": transaction_id,
                    "customer_id": customer_id,
                    "date": order_date,
                    "product_id": product["product_id"],
                    "sku": product["sku"],
                    "product_name": product["product_name"],
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "discount": discount_pct,
                    "net_amount": net,
                    "category": product["category"],
                    "brand": product["brand"],
                    "color": product["color"],
                    "size": product["size"],
                    "store": store,
                    "channel": channel,
                })
                lines_written += 1

        first_purchase = order_dates[0] if order_dates else None
        consent = rng.random() < 0.84
        customers.append({
            "customer_id": customer_id,
            "first_name": first,
            "last_name": last,
            "email": f"{first.lower()}.{last.lower().replace(' ', '')}@{rng.choice(['gmail.com', 'libero.it', 'icloud.com', 'outlook.com'])}",
            "phone": f"+39 3{rng.randint(10, 99)} {rng.randint(1000000, 9999999)}",
            "gender": "Donna" if gender == "F" else "Uomo",
            "age": rng.randint(24, 68),
            "city": city,
            "country": country,
            "store": rng.choice(STORES),
            "sizes": f"{clothing_size}; {shoe_size}",
            "colors": "; ".join(palette[:3]),
            "channel": rng.choice(["Boutique", "Boutique", "Online", "Referral"]),
            "consent": "Yes" if consent else "No",
            "notes": _persona_note(rng, persona, favourite_brand, favourite_category),
            "first_purchase_date": first_purchase,
            "_persona": persona.key,
            "_lines": lines_written,
        })

    customers_frame = pd.DataFrame(customers)
    transactions_frame = pd.DataFrame(transactions)

    # Drop the internal persona columns from what the "boutique" exports —
    # the engine must rediscover the behaviour from the ledger alone.
    customers_frame = customers_frame.drop(columns=[c for c in customers_frame.columns
                                                    if c.startswith("_")])
    return customers_frame, transactions_frame


def _pick_city(rng: random.Random) -> tuple[str, str]:
    choice = _weighted_choice(rng, [((c, country), w) for c, country, w in CITIES])
    return choice


def _persona_palette(rng: random.Random, persona: Persona) -> list[str]:
    neutrals = [c for c, _ in COLORS if c in NEUTRALS]
    colourful = [c for c, _ in COLORS if c not in NEUTRALS]
    rng.shuffle(neutrals)
    rng.shuffle(colourful)
    n_neutral = 3 if rng.random() < persona.neutral_bias else 1
    return neutrals[:n_neutral] + colourful[: max(1, 4 - n_neutral)]


def _pick_product(rng, persona, by_brand, by_category, products, favourite_brand,
                  second_brand, favourite_category, second_category, palette,
                  clothing_size, shoe_size, price_multiplier, order_date,
                  exclude: set[str] | None = None):
    """Choose a product the way this persona actually shops."""
    pool: list[dict] = []
    roll = rng.random()
    if roll < persona.brand_focus:
        pool = by_brand.get(favourite_brand, [])
    elif roll < persona.brand_focus + 0.15:
        pool = by_brand.get(second_brand, [])
    if not pool:
        roll_c = rng.random()
        if roll_c < persona.category_focus:
            pool = by_category.get(favourite_category, [])
        elif roll_c < persona.category_focus + 0.20:
            pool = by_category.get(second_category, [])
    if not pool:
        pool = products

    # Only consider pieces that existed at the time of the sale.
    exclude = exclude or set()
    candidates = [p for p in pool
                  if p["arrival_date"] <= order_date and p["product_id"] not in exclude]
    if not candidates:
        candidates = [p for p in products
                      if p["arrival_date"] <= order_date and p["product_id"] not in exclude]
    if not candidates:
        return None

    scored: list[tuple[dict, float]] = []
    for product in candidates:
        weight = 0.25 + product["_desirability"]
        if product["color"] in palette:
            weight *= 2.4
        size = product["size"]
        if size in CLOTHING_SIZES:
            weight *= 3.0 if size == clothing_size else 0.35
        elif size in SHOE_SIZES:
            weight *= 3.0 if size == shoe_size else 0.30
        # price fit against the persona's ceiling
        target = 420 * price_multiplier
        ratio = product["price"] / max(target, 50)
        weight *= float(np.exp(-((np.log(max(ratio, 0.05))) ** 2) / 0.9))
        # older stock is naturally less attractive
        weight *= 1.0 if product["_age_days"] < 200 else 0.45
        scored.append((product, max(weight, 0.001)))

    return _weighted_choice(rng, scored)


def _persona_note(rng, persona: Persona, brand: str, category: str) -> str:
    templates = {
        "champion": f"Regular client. Strong {brand} follower, always first to see new {category.lower()}.",
        "vip_full_price": f"Buys at full price. Prefers {brand}. Dislikes sale periods.",
        "brand_devotee": f"Almost exclusively {brand}.",
        "dormant_vip": f"High spender, has not visited recently. Loved {category.lower()}.",
        "steady_regular": f"Consistent client, mostly {category.lower()}.",
        "markdown_hunter": "Waits for the sale. Responds well to private sale invitations.",
        "emerging": f"Growing spend, interested in {brand}.",
        "new_customer": "Recent first purchase — follow up.",
        "occasional": "Buys once or twice a year.",
        "lapsed": "No contact for a long time.",
    }
    return templates.get(persona.key, "")


# --------------------------------------------------------------------------- #
def _finalise_inventory(products: list[dict], transactions: pd.DataFrame,
                        rng: random.Random, today: date) -> pd.DataFrame:
    """Derive current stock from initial buy minus what actually sold."""
    sold = (
        transactions.groupby("product_id")["quantity"].sum().to_dict()
        if not transactions.empty else {}
    )

    rows: list[dict[str, Any]] = []
    for product in products:
        units_sold = float(sold.get(product["product_id"], 0))
        # products bought deeper when they were expected to perform
        initial = product["_base_units"] + (2 if product["_desirability"] > 0.7 else 0)
        stock = max(0, int(round(initial + units_sold * 0.55 - units_sold)))
        # keep some ageing stock genuinely on hand so dead stock is real
        if product["_age_days"] > 260 and units_sold <= 1:
            stock = max(stock, rng.randint(1, 4))
        rows.append({
            "product_id": product["product_id"],
            "sku": product["sku"],
            "product_name": product["product_name"],
            "description": f"{product['brand']} {product['subcategory']} {product['category'].lower()}",
            "category": product["category"],
            "subcategory": product["subcategory"],
            "brand": product["brand"],
            "gender": product["gender"],
            "price": product["price"],
            "original_price": product["original_price"],
            "cost": product["cost"],
            "stock": stock,
            "size": product["size"],
            "color": product["color"],
            "season": product["season"],
            "collection": product["collection"],
            "arrival_date": product["arrival_date"],
            "supplier": product["supplier"],
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
def demo_csv_bytes() -> dict[str, bytes]:
    """The demo data as CSV files, for testing the real import path end to end."""
    data = generate_demo_dataset()
    return {
        name: frame.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
        for name, frame in data.items()
    }
