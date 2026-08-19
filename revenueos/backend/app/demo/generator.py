"""Synthetic but *correlated* boutique data.

Random data makes an analytics product look broken: every customer scores the
same and no recommendation is defensible. So each customer here is generated
from a persona with real preferences, and their transactions are drawn from
those preferences. That means the analytics engine has genuine structure to
find — brand loyalists, dormant VIPs, discount hunters, and stock that
legitimately becomes dead.

Deterministic: the same seed always produces the same boutique.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

ANCHOR = date(2026, 8, 17)   # "today" for the demo dataset

FIRST_NAMES = [
    "Giulia", "Marco", "Sofia", "Alessandro", "Chiara", "Lorenzo", "Martina", "Andrea",
    "Francesca", "Matteo", "Elena", "Davide", "Beatrice", "Simone", "Alice", "Federico",
    "Valentina", "Riccardo", "Camilla", "Tommaso", "Ilaria", "Nicolò", "Sara", "Luca",
    "Anna", "Pietro", "Greta", "Stefano", "Bianca", "Emanuele", "Silvia", "Gabriele",
    "Claudia", "Antonio", "Margherita", "Filippo", "Eleonora", "Michele", "Arianna", "Paolo",
    "Camille", "Louis", "Charlotte", "Olivia", "James", "Sophie", "Émilie", "Thomas",
]
LAST_NAMES = [
    "Rossi", "Bianchi", "Ferrari", "Romano", "Conti", "Ricci", "Marino", "Greco",
    "Bruno", "Gallo", "Costa", "Fontana", "Moretti", "Barbieri", "Rizzo", "Lombardi",
    "Colombo", "Esposito", "Serra", "Villa", "De Luca", "Mancini", "Longo", "Martini",
    "Dubois", "Bernard", "Laurent", "Moreau", "Brown", "Taylor", "Wilson", "Clarke",
]
CITIES = [
    ("Milano", "Italy"), ("Roma", "Italy"), ("Firenze", "Italy"), ("Torino", "Italy"),
    ("Bologna", "Italy"), ("Verona", "Italy"), ("Como", "Italy"), ("Napoli", "Italy"),
    ("Paris", "France"), ("Lyon", "France"), ("London", "United Kingdom"), ("Madrid", "Spain"),
    ("München", "Germany"), ("Lugano", "Switzerland"),
]
STORES = ["Milano Montenapoleone", "Milano Brera", "Firenze Tornabuoni"]

# (brand, tier) — tier drives price level and who buys it.
BRANDS = [
    ("Totême", "luxury"), ("Max Mara", "luxury"), ("Loro Piana", "luxury"),
    ("Jil Sander", "luxury"), ("The Row", "luxury"),
    ("Aspesi", "premium"), ("Herno", "premium"), ("Fabiana Filippi", "premium"),
    ("Marni", "premium"), ("Golden Goose", "premium"), ("Autry", "premium"),
    ("A.P.C.", "contemporary"), ("Closed", "contemporary"), ("American Vintage", "contemporary"),
    ("Sessùn", "contemporary"), ("Bellerose", "contemporary"),
]
BRAND_TIER = dict(BRANDS)

CATALOGUE = {
    "Ready-to-Wear": {
        "items": ["Wool Coat", "Cashmere Knit", "Silk Blouse", "Tailored Blazer", "Pleated Skirt",
                  "Wide Trousers", "Midi Dress", "Quilted Jacket", "Trench Coat", "Merino Cardigan",
                  "Poplin Shirt", "Denim Jacket", "Padded Gilet", "Jersey Top"],
        "price": (180, 1450), "sizes": ["XS", "S", "M", "L", "XL"],
    },
    "Leather Goods": {
        "items": ["Structured Tote", "Soft Hobo", "Mini Crossbody", "Top Handle Bag",
                  "Bucket Bag", "Card Holder", "Continental Wallet", "Belt Bag"],
        "price": (220, 2200), "sizes": ["One Size"],
    },
    "Shoes": {
        "items": ["Leather Loafer", "Ankle Boot", "Knee Boot", "Low Sneaker", "Slingback Pump",
                  "Flat Sandal", "Chelsea Boot", "Ballerina Flat"],
        "price": (190, 890), "sizes": ["36", "37", "38", "39", "40", "41"],
    },
    "Accessories": {
        "items": ["Cashmere Scarf", "Leather Belt", "Wool Hat", "Silk Foulard",
                  "Leather Gloves", "Sunglasses", "Fine Chain Necklace"],
        "price": (75, 620), "sizes": ["One Size", "S", "M", "L"],
    },
    "Travel": {
        "items": ["Weekender Bag", "Cabin Trolley", "Garment Bag", "Travel Pouch Set"],
        "price": (280, 1850), "sizes": ["One Size"],
    },
}

COLORS = ["Black", "Camel", "Ivory", "Navy", "Grey", "Beige", "Brown", "Green", "Burgundy",
          "White", "Taupe", "Red"]
NEUTRALS = ["Black", "Camel", "Ivory", "Navy", "Grey", "Beige", "Taupe", "Brown"]
SEASONS = ["SS25", "FW25", "SS26", "FW26"]

# Personas: the correlations that make the data worth analysing.
PERSONAS = [
    # name, weight, price_multiplier, orders/yr, brand loyalty, colour discipline, discount appetite
    ("vic",            0.08, 2.4, 6.5, 0.75, 0.75, 0.05),
    ("loyal_premium",  0.16, 1.4, 4.2, 0.60, 0.60, 0.15),
    ("brand_devotee",  0.10, 1.5, 3.4, 0.92, 0.45, 0.10),
    ("steady",         0.22, 1.0, 2.6, 0.35, 0.40, 0.25),
    ("discount_hunter",0.12, 0.7, 3.0, 0.20, 0.25, 0.85),
    ("occasional",     0.16, 0.9, 1.3, 0.25, 0.30, 0.35),
    ("newcomer",       0.09, 1.0, 1.1, 0.20, 0.30, 0.30),
    ("dormant_vic",    0.07, 2.1, 4.8, 0.70, 0.70, 0.10),
]


def _weighted_choice(rng: random.Random, options: list[tuple[str, float, Any]]) -> Any:
    total = sum(o[1] for o in options)
    roll = rng.random() * total
    acc = 0.0
    for opt in options:
        acc += opt[1]
        if roll <= acc:
            return opt
    return options[-1]


def generate(seed: int = 7, n_customers: int = 160, n_products: int = 300,
             target_transactions: int = 2200) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    products = _make_products(rng, n_products)
    customers, transactions = _make_customers_and_sales(rng, products, n_customers, target_transactions)
    return {"customers": customers, "transactions": transactions, "inventory": products}


def _make_products(rng: random.Random, n: int) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    seen: set[str] = set()
    idx = 0
    while len(products) < n:
        idx += 1
        category = rng.choices(list(CATALOGUE), weights=[38, 22, 20, 14, 6])[0]
        spec = CATALOGUE[category]
        item = rng.choice(spec["items"])
        brand, tier = rng.choice(BRANDS)
        tier_mult = {"luxury": 1.9, "premium": 1.15, "contemporary": 0.72}[tier]

        lo, hi = spec["price"]
        base = rng.uniform(lo, hi) * tier_mult
        price = round(base / 10) * 10
        cost = round(price * rng.uniform(0.34, 0.48), 2)

        color = rng.choice(NEUTRALS if rng.random() < 0.62 else COLORS)
        size = rng.choice(spec["sizes"])
        season = rng.choices(SEASONS, weights=[12, 22, 30, 36])[0]
        season_age = {"SS25": (430, 620), "FW25": (300, 430), "SS26": (110, 300), "FW26": (3, 110)}[season]
        arrival = ANCHOR - timedelta(days=rng.randint(*season_age))

        name = f"{item}"
        sku = f"{category[:2].upper()}-{brand[:3].upper()}-{idx:04d}"
        if sku in seen:
            continue
        seen.add(sku)

        # Older seasons hold less stock, but a slice deliberately over-stocks and dies.
        base_stock = rng.randint(1, 9)
        if season in {"SS25", "FW25"} and rng.random() < 0.45:
            base_stock += rng.randint(2, 8)

        products.append({
            "sku": sku,
            "product_name": name,
            "description": f"{brand} {name.lower()} in {color.lower()}",
            "category": category,
            "subcategory": item,
            "brand": brand,
            "gender": "Donna",
            "price": float(price),
            "original_price": float(price if season in {"SS26", "FW26"} else round(price * 1.25 / 10) * 10),
            "cost": cost,
            "stock": base_stock,
            "size": size,
            "color": color,
            "season": season,
            "collection": season,
            "arrival_date": arrival,
            "supplier": brand,
            "store": rng.choice(STORES),
            "_tier": tier,
        })
    return products


def _make_customers_and_sales(rng, products, n_customers, target_transactions):
    customers: list[dict[str, Any]] = []
    transactions: list[dict[str, Any]] = []
    persona_options = [(p[0], p[1], p) for p in PERSONAS]
    used_names: set[str] = set()

    tx_counter = 0
    for i in range(n_customers):
        _, _, persona = _weighted_choice(rng, persona_options)
        pname, _, price_mult, orders_yr, loyalty, color_discipline, discount_appetite = persona

        for _ in range(40):
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            if name not in used_names:
                break
        used_names.add(name)

        cid = f"CL-{1000 + i}"
        city, country = rng.choice(CITIES)
        store = rng.choice(STORES)

        # Each customer has a home category plus an occasional second one.
        home_cat = rng.choices(list(CATALOGUE), weights=[36, 24, 20, 14, 6])[0]
        second_cat = rng.choice([c for c in CATALOGUE if c != home_cat])
        fav_brand = rng.choice([b for b, t in BRANDS
                                if (t == "luxury" if price_mult > 1.6 else t != "luxury")])
        fav_colors = rng.sample(NEUTRALS, 2) if color_discipline > 0.5 else rng.sample(COLORS, 3)
        size_pref = {
            "Ready-to-Wear": rng.choice(["XS", "S", "M", "L"]),
            "Shoes": rng.choice(["37", "38", "39", "40"]),
            "Accessories": rng.choice(["One Size", "M"]),
        }

        tenure_days = rng.randint(120, 1500) if pname != "newcomer" else rng.randint(20, 110)
        first_purchase = ANCHOR - timedelta(days=tenure_days)
        years = max(0.25, tenure_days / 365.25)
        n_orders = max(1, int(round(orders_yr * years * rng.uniform(0.7, 1.3))))
        n_orders = min(n_orders, 34)

        # Dormant personas simply stop earlier; that is what makes them detectable.
        if pname == "dormant_vic":
            active_until = ANCHOR - timedelta(days=rng.randint(150, 330))
        elif pname == "occasional":
            active_until = ANCHOR - timedelta(days=rng.randint(20, 220))
        else:
            active_until = ANCHOR - timedelta(days=rng.randint(2, 70))
        span = max(1, (active_until - first_purchase).days)

        order_days = sorted(rng.sample(range(span + 1), min(n_orders, span + 1))) if span > 0 else [0]
        # Consent is messy in real boutiques: some customers agree to everything,
        # some only to email, some withdrew entirely, and some were never asked.
        consent = rng.random() < (0.9 if price_mult > 1.3 else 0.72)
        opted_out = rng.random() < 0.04
        email_ok = consent and rng.random() < 0.92
        whatsapp_ok = consent and rng.random() < 0.55
        phone_ok = consent and rng.random() < 0.35
        sms_ok = consent and rng.random() < 0.30
        # Recently contacted customers exist, and the frequency cap must hold them.
        contacted_on = (ANCHOR - timedelta(days=rng.randint(1, 60))
                        if consent and rng.random() < 0.22 else None)

        for order_idx, offset in enumerate(order_days):
            order_date = first_purchase + timedelta(days=offset)
            if order_date > ANCHOR:
                continue
            tx_counter += 1
            order_id = f"ORD-{tx_counter:06d}"
            lines = rng.choices([1, 2, 3], weights=[62, 28, 10])[0]

            for _ in range(lines):
                category = home_cat if rng.random() < 0.74 else second_cat
                pool = [p for p in products if p["category"] == category]
                if not pool:
                    continue

                # Size first: people are the size they are, so this constraint
                # binds hardest and must not be traded away for a brand match.
                want_size = size_pref.get(category)
                if want_size:
                    sized = [p for p in pool if p["size"] == want_size]
                    pool = sized or pool
                # Brand loyalty
                if rng.random() < loyalty:
                    branded = [p for p in pool if p["brand"] == fav_brand]
                    pool = branded or pool
                # Colour discipline
                if rng.random() < color_discipline:
                    colored = [p for p in pool if p["color"] in fav_colors]
                    pool = colored or pool
                # Price level appropriate to the persona
                target_price = 420 * price_mult
                pool = sorted(pool, key=lambda p: abs(p["price"] - target_price))[:max(4, len(pool) // 3)]
                product = rng.choice(pool)

                qty = 1
                unit = product["price"]
                discount_rate = 0.0
                if rng.random() < discount_appetite:
                    discount_rate = rng.choice([0.1, 0.15, 0.2, 0.3])
                line_total = round(unit * qty * (1 - discount_rate), 2)

                transactions.append({
                    "transaction_id": order_id,
                    "customer_id": cid,
                    "date": order_date,
                    "sku": product["sku"],
                    "product": product["product_name"],
                    "category": product["category"],
                    "brand": product["brand"],
                    "color": product["color"],
                    "size": product["size"],
                    "quantity": qty,
                    "unit_price": unit,
                    "discount": round(unit * discount_rate, 2) if discount_rate else 0.0,
                    "line_total": line_total,
                    "store": store,
                    "advisor": f"ADV-{rng.randint(1, 4):02d}",
                })

        spent = sum(t["line_total"] for t in transactions if t["customer_id"] == cid)
        my_tx = [t for t in transactions if t["customer_id"] == cid]
        last_date = max((t["date"] for t in my_tx), default=first_purchase)
        orders_done = len({t["transaction_id"] for t in my_tx})

        customers.append({
            "customer_id": cid,
            "first_name": name.split()[0],
            "last_name": name.split()[-1],
            "name": name,
            "email": f"{name.lower().replace(' ', '.').replace('à','a').replace('è','e')}@example.com",
            "phone": f"+39 3{rng.randint(10, 99)} {rng.randint(1000000, 9999999)}",
            "gender": "Donna",
            "city": city,
            "country": country,
            "store": store,
            "total_spend": round(spent, 2),
            "num_purchases": orders_done,
            "avg_order_value": round(spent / orders_done, 2) if orders_done else None,
            "first_purchase_date": first_purchase,
            "last_purchase_date": last_date,
            "preferred_category": home_cat,
            "preferred_brand": fav_brand,
            "size": size_pref.get(home_cat),
            "color": fav_colors[0],
            "marketing_consent": consent,
            "email_consent": email_ok,
            "whatsapp_consent": whatsapp_ok,
            "phone_consent": phone_ok,
            "sms_consent": sms_ok,
            "do_not_contact": opted_out,
            "last_contacted_date": contacted_on,
            "channel": rng.choice(["Boutique", "Boutique", "Online", "Referral"]),
            "notes": None,
            "_persona": pname,
        })

    # Top up volume if the personas came out light, keeping the same structure.
    guard = 0
    while len(transactions) < target_transactions and guard < 4000:
        guard += 1
        cust = rng.choice(customers)
        pool = [p for p in products if p["category"] == cust["preferred_category"]]
        if not pool:
            continue
        product = rng.choice(pool)
        when = ANCHOR - timedelta(days=rng.randint(5, 700))
        tx_counter += 1
        transactions.append({
            "transaction_id": f"ORD-{tx_counter:06d}",
            "customer_id": cust["customer_id"],
            "date": when,
            "sku": product["sku"],
            "product": product["product_name"],
            "category": product["category"],
            "brand": product["brand"],
            "color": product["color"],
            "size": product["size"],
            "quantity": 1,
            "unit_price": product["price"],
            "discount": 0.0,
            "line_total": product["price"],
            "store": cust["store"],
            "advisor": f"ADV-{rng.randint(1, 4):02d}",
        })
        cust["total_spend"] = round((cust["total_spend"] or 0) + product["price"], 2)
        cust["num_purchases"] = (cust["num_purchases"] or 0) + 1
        if when > cust["last_purchase_date"]:
            cust["last_purchase_date"] = when

    # Reduce stock for what actually sold, so sell-through is coherent.
    sold: dict[str, int] = {}
    for t in transactions:
        sold[t["sku"]] = sold.get(t["sku"], 0) + t["quantity"]
    for p in products:
        units = sold.get(p["sku"], 0)
        if units:
            p["stock"] = max(0, p["stock"] - units // 2)
        p.pop("_tier", None)

    for c in customers:
        c.pop("_persona", None)

    return customers, transactions


def to_csv_rows(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Render demo records as strings, so they travel the real import path."""
    out = []
    for r in records:
        row = {}
        for k, v in r.items():
            if v is None:
                row[k] = ""
            elif isinstance(v, date):
                row[k] = v.isoformat()
            elif isinstance(v, bool):
                row[k] = "Yes" if v else "No"
            else:
                row[k] = str(v)
        out.append(row)
    return out
