"""Opportunity engine: turn metrics into ranked, actionable revenue plays.

Every opportunity is discovered deterministically from computed metrics and
carries the customers/products it refers to, so the UI can drill straight in and
the AI layer can narrate it without inventing anything.

    Opportunity Score = probability × value × urgency × confidence  (0-100)
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from . import matching

# How believable each play is, from observed retail response rates. Deliberately
# conservative: better to under-promise the boutique than inflate a forecast.
_BASE_PROBABILITY = {
    "overdue_vip": 0.30,
    "reactivation": 0.12,
    "dead_stock": 0.15,
    "new_arrival": 0.22,
    "cross_sell": 0.18,
    "brand_drop": 0.25,
    "size_gap": 0.20,
    "category_momentum": 0.20,
}


def _plural_days(value: int | None) -> str:
    """'1 day', not '1 days'."""
    if value is None:
        return "recently"
    return "1 day" if value == 1 else f"{value} days"


def _urgency(days_overdue: float | None, cap: float = 2.5) -> float:
    if days_overdue is None:
        return 0.5
    return max(0.2, min(1.0, days_overdue / cap))


def _confidence_value(label: str) -> float:
    return {"High": 1.0, "Medium": 0.8, "Low": 0.55}.get(label, 0.7)


def _score(probability: float, value: float | None, urgency: float, confidence: float,
           value_scale: float) -> int:
    """Normalise the four drivers into a 0-100 priority."""
    if not value or value <= 0:
        value_component = 0.25
    else:
        value_component = min(1.0, value / value_scale) if value_scale > 0 else 0.5
    raw = (0.32 * min(1.0, probability / 0.35)
           + 0.34 * value_component
           + 0.20 * urgency
           + 0.14 * confidence)
    return int(round(max(0, min(100, raw * 100))))


def _consented(profiles: list[dict]) -> list[dict]:
    """Customers we may actually contact. Unknown consent is not consent."""
    return [p for p in profiles if p.get("marketing_consent") is True]


def _contactable(p: dict) -> bool:
    return p.get("marketing_consent") is True


def detect(
    profiles: list[dict[str, Any]],
    products: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    as_of: date | None = None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    if as_of is None:
        tx_dates = [t["date"] for t in transactions if t.get("date")]
        as_of = max(tx_dates) if tx_dates else date.today()

    spends = [p["total_spend"] for p in profiles if p.get("total_spend")]
    value_scale = (statistics.quantiles(spends, n=10)[-1] if len(spends) >= 10
                   else (max(spends) if spends else 1000.0)) or 1000.0

    found: list[dict[str, Any]] = []
    found += _overdue_high_value(profiles, products, value_scale)
    found += _dead_stock_rescue(profiles, products, value_scale)
    found += _new_arrival_targets(profiles, products, as_of, value_scale)
    found += _reactivation(profiles, products, value_scale)
    found += _cross_sell(profiles, products, value_scale)
    found += _category_momentum(transactions, products, as_of, value_scale)
    found += _size_gaps(profiles, products, value_scale)

    # Every opportunity carries both a headline impact (the full prize) and an
    # expected value (impact × probability). Dashboards use the expected value,
    # so the boutique is never shown a number it has little chance of realising.
    for opp in found:
        impact = opp.get("impact") or 0
        opp["expected_value"] = round(impact * opp.get("probability", 0.15), 2)

    found.sort(key=lambda o: -o["score"])
    return found[:limit]


# --------------------------------------------------------------- detectors ---

def _overdue_high_value(profiles, products, value_scale) -> list[dict]:
    candidates = [
        p for p in profiles
        if (p.get("overdue_ratio") or 0) >= 1.25
        and (p.get("value_percentile") or 0) >= 0.6
        and p.get("segment") not in {"Lost"}
    ]
    if not candidates:
        return []
    candidates.sort(key=lambda p: -((p.get("total_spend") or 0) * (p.get("overdue_ratio") or 1)))
    top = candidates[:20]

    # One successful outreach yields roughly one basket — not a whole year of
    # that customer's spend. Annual value is potential, not this week's prize.
    value = sum(p.get("avg_order_value") or 0 for p in top)
    annual_at_stake = sum(p.get("potential_annual_value") or 0 for p in top)
    avg_overdue = statistics.mean(p["overdue_ratio"] for p in top)
    reachable = [p for p in top if _contactable(p)]
    probability = _BASE_PROBABILITY["overdue_vip"] * (0.5 + 0.5 * len(reachable) / max(1, len(top)))
    confidence = statistics.mean(_confidence_value(p.get("data_confidence", "Medium")) for p in top)

    entities = []
    for p in top[:10]:
        rec = matching.best_products_for_customer(p, products, limit=1)
        entities.append({
            "type": "customer",
            "id": p["customer_id"],
            "name": p["name"],
            "detail": (f"{p['overdue_ratio']:.1f}× past their usual "
                       f"{p['cadence_days']:.0f}-day cycle" if p.get("cadence_days")
                       else f"{p.get('recency_days')} days since last purchase"),
            "value": p.get("potential_annual_value") or p.get("avg_order_value"),
            "suggested_product": rec[0]["product_name"] if rec else None,
            "match_pct": rec[0]["match_pct"] if rec else None,
            "contactable": _contactable(p),
        })

    return [{
        "id": "overdue-high-value",
        "type": "overdue_vip",
        "title": f"{len(top)} high-value customers are overdue",
        "explanation": (
            f"These customers rank in your top spending tier and are on average "
            f"{avg_overdue:.1f}× past their normal repurchase interval. "
            f"{len(reachable)} of them have marketing consent on file."
        ),
        "impact": round(value, 2) if value else None,
        "impact_basis": "One average basket per customer, the realistic prize from a single contact",
        "annual_value_at_stake": round(annual_at_stake, 2) if annual_at_stake else None,
        "probability": round(probability, 3),
        "urgency": round(_urgency(avg_overdue), 3),
        "confidence": round(confidence, 3),
        "score": _score(probability, value, _urgency(avg_overdue), confidence, value_scale * 2),
        "action": "Personal outreach this week — call or message before they drift further.",
        "entities": entities,
        "customer_ids": [p["customer_id"] for p in top],
    }]


def _dead_stock_rescue(profiles, products, value_scale) -> list[dict]:
    stuck = [p for p in products
             if p.get("risk_class") in {"Dead Stock", "At Risk"} and (p.get("stock") or 0) > 0]
    if not stuck:
        return []
    stuck.sort(key=lambda p: -(p.get("stock_value") or 0))
    focus = stuck[:12]
    tied_up = sum(p.get("stock_value") or 0 for p in focus)

    audience: dict[str, dict] = {}
    entities = []
    for prod in focus[:6]:
        buyers = matching.best_customers_for_product(prod, profiles, limit=6, min_score=0.45)
        for b in buyers:
            audience.setdefault(b["customer_id"], b)
        entities.append({
            "type": "product",
            "id": prod["sku"],
            "name": prod["product_name"],
            "detail": prod.get("risk_reason") or "Ageing stock",
            "value": prod.get("stock_value"),
            "matched_customers": len(buyers),
            "top_match": buyers[0]["customer_name"] if buyers else None,
            "top_match_pct": buyers[0]["match_pct"] if buyers else None,
        })

    if not audience:
        return []
    probability = _BASE_PROBABILITY["dead_stock"]
    recoverable = tied_up * 0.45     # realistic partial recovery, not the full value
    urgency = 0.8
    confidence = 0.75

    return [{
        "id": "dead-stock-rescue",
        "type": "dead_stock",
        "title": f"€{tied_up:,.0f} of stock is ageing — {len(audience)} customers match it",
        "explanation": (
            f"{len(focus)} products are classified At Risk or Dead Stock. Rather than "
            f"discounting, {len(audience)} customers show genuine affinity for these pieces "
            "and can be approached personally first."
        ),
        "impact": round(recoverable, 2),
        "impact_basis": "45% of tied-up stock value, the share typically recovered by targeted outreach",
        "probability": probability,
        "urgency": urgency,
        "confidence": confidence,
        "score": _score(probability, recoverable, urgency, confidence, value_scale * 8),
        "action": "Run a targeted clienteling push before applying any markdown.",
        "entities": entities,
        "product_skus": [p["sku"] for p in focus],
        "customer_ids": list(audience)[:40],
    }]


def _new_arrival_targets(profiles, products, as_of, value_scale) -> list[dict]:
    fresh = []
    for p in products:
        if not p.get("arrival_date") or (p.get("stock") or 0) <= 0:
            continue
        age = p.get("days_in_stock")
        if age is not None and age <= 60:
            fresh.append(p)
    if not fresh:
        return []
    fresh.sort(key=lambda p: -(p.get("price") or 0))

    out = []
    for prod in fresh[:4]:
        buyers = matching.best_customers_for_product(prod, profiles, limit=12, min_score=0.5)
        if len(buyers) < 3:
            continue
        value = sum(matching.expected_value(b, next(p for p in profiles if p["customer_id"] == b["customer_id"]))
                    or 0 for b in buyers)
        reachable = sum(1 for b in buyers
                        if next(p for p in profiles if p["customer_id"] == b["customer_id"]).get("marketing_consent") is True)
        probability = _BASE_PROBABILITY["new_arrival"]
        urgency = 0.7
        confidence = statistics.mean(_confidence_value(b["data_confidence"]) for b in buyers)
        out.append({
            "id": f"new-arrival-{prod['sku']}",
            "type": "new_arrival",
            "title": f"{len(buyers)} customers match the new {prod['product_name']}",
            "explanation": (
                f"{prod['product_name']}"
                + (f" ({prod['brand']})" if prod.get("brand") else "")
                + f" arrived {_plural_days(prod.get('days_in_stock'))} ago. "
                f"{len(buyers)} customers show strong affinity; {reachable} have consent on file."
            ),
            "impact": round(value, 2) if value else None,
            "impact_basis": "Sum of price × modelled conversion for each matched customer",
            "probability": probability,
            "urgency": urgency,
            "confidence": round(confidence, 3),
            "score": _score(probability, value, urgency, confidence, value_scale * 4),
            "action": f"Message the top {min(8, len(buyers))} matches with a personal note and hold the piece.",
            "entities": [{
                "type": "customer", "id": b["customer_id"], "name": b["customer_name"],
                "detail": "; ".join(b["why"][:2]) or "Strong affinity match",
                "value": prod.get("price"), "match_pct": b["match_pct"],
                "contactable": next(p for p in profiles if p["customer_id"] == b["customer_id"]).get("marketing_consent") is True,
            } for b in buyers[:10]],
            "product_skus": [prod["sku"]],
            "customer_ids": [b["customer_id"] for b in buyers],
        })
    return out


def _reactivation(profiles, products, value_scale) -> list[dict]:
    dormant = [p for p in profiles
               if p.get("segment") in {"Sleeping", "At Risk"}
               and (p.get("total_spend") or 0) > 0
               and (p.get("value_percentile") or 0) >= 0.35]
    if len(dormant) < 3:
        return []
    dormant.sort(key=lambda p: -(p.get("total_spend") or 0))
    top = dormant[:40]
    value = sum(p.get("avg_order_value") or 0 for p in top)
    reachable = [p for p in top if _contactable(p)]
    probability = _BASE_PROBABILITY["reactivation"] * (0.4 + 0.6 * len(reachable) / max(1, len(top)))
    urgency = 0.55
    confidence = 0.7

    return [{
        "id": "reactivation-wave",
        "type": "reactivation",
        "title": f"€{value:,.0f} sitting in {len(top)} dormant customers",
        "explanation": (
            f"{len(top)} customers with real spending history have gone quiet. At their own "
            f"average basket, re-engaging them is worth €{value:,.0f} in potential revenue. "
            f"{len(reachable)} are contactable today."
        ),
        "impact": round(value, 2),
        "impact_basis": "One average basket from each dormant customer if they return",
        "probability": round(probability, 3),
        "urgency": urgency,
        "confidence": confidence,
        "score": _score(probability, value * probability, urgency, confidence, value_scale * 2),
        "action": "Build a reactivation campaign around each customer's own category.",
        "entities": [{
            "type": "customer", "id": p["customer_id"], "name": p["name"],
            "detail": f"{p.get('recency_days')} days quiet · {p.get('segment')}",
            "value": p.get("avg_order_value"), "contactable": _contactable(p),
        } for p in top[:10]],
        "customer_ids": [p["customer_id"] for p in top],
    }]


def _cross_sell(profiles, products, value_scale) -> list[dict]:
    loyal = [p for p in profiles
             if p.get("segment") in {"Loyal", "Champions", "VIP"}
             and len(p.get("category_affinity") or {}) == 1
             and (p.get("order_count") or 0) >= 3]
    if len(loyal) < 3:
        return []

    entities, total = [], 0.0
    for p in loyal[:12]:
        owned = next(iter(p["category_affinity"]))
        recs = [m for m in matching.best_products_for_customer(p, products, limit=4, min_score=0.4)
                if m.get("category") and m["category"] != owned]
        if not recs:
            continue
        best = recs[0]
        total += matching.expected_value(best, p) or 0
        entities.append({
            "type": "customer", "id": p["customer_id"], "name": p["name"],
            "detail": f"Buys only {owned} — {best['product_name']} extends the relationship",
            "value": best.get("price"), "match_pct": best["match_pct"],
            "suggested_product": best["product_name"], "contactable": _contactable(p),
        })
    if len(entities) < 3:
        return []

    probability = _BASE_PROBABILITY["cross_sell"]
    return [{
        "id": "cross-sell-single-category",
        "type": "cross_sell",
        "title": f"{len(entities)} loyal customers buy only one category",
        "explanation": (
            "These are proven, repeat customers whose spend is concentrated in a single "
            "category. Introducing an adjacent category is the lowest-risk way to grow "
            "their basket."
        ),
        "impact": round(total, 2) if total else None,
        "impact_basis": "Recommended product price × modelled conversion",
        "probability": probability,
        "urgency": 0.4,
        "confidence": 0.75,
        "score": _score(probability, total, 0.4, 0.75, value_scale * 3),
        "action": "Style a second category into their next conversation.",
        "entities": entities[:10],
        "customer_ids": [e["id"] for e in entities],
    }]


def _category_momentum(transactions, products, as_of, value_scale) -> list[dict]:
    dated = [t for t in transactions if t.get("date") and t.get("category")]
    if len(dated) < 40:
        return []
    recent_cut = as_of.toordinal() - 30
    prior_cut = as_of.toordinal() - 90

    recent: dict[str, float] = defaultdict(float)
    prior: dict[str, float] = defaultdict(float)
    for t in dated:
        o = t["date"].toordinal()
        if o > recent_cut:
            recent[str(t["category"])] += t["line_total"]
        elif o > prior_cut:
            prior[str(t["category"])] += t["line_total"]

    out = []
    for cat, rev in sorted(recent.items(), key=lambda kv: -kv[1])[:6]:
        baseline = prior.get(cat, 0) / 2  # prior window is twice as long
        if baseline <= 0 or rev < baseline * 1.4 or rev < 200:
            continue
        lift = (rev - baseline) / baseline
        in_stock = [p for p in products
                    if p.get("category") == cat and (p.get("stock") or 0) > 0]
        stock_value = sum(p.get("stock_value") or 0 for p in in_stock)
        probability = _BASE_PROBABILITY["category_momentum"]
        out.append({
            "id": f"momentum-{cat}",
            "type": "category_momentum",
            "title": f"{cat} is accelerating (+{lift:.0%} in 30 days)",
            "explanation": (
                f"{cat} generated €{rev:,.0f} in the last 30 days versus a €{baseline:,.0f} "
                f"run-rate in the prior period. You hold €{stock_value:,.0f} of {cat.lower()} "
                f"stock across {len(in_stock)} products to ride the trend."
            ),
            "impact": round(rev * 0.3, 2),
            "impact_basis": "30% uplift on the current 30-day run-rate if the trend is supported",
            "probability": probability,
            "urgency": 0.65,
            "confidence": 0.7,
            "score": _score(probability, rev * 0.3, 0.65, 0.7, value_scale * 4),
            "action": f"Give {cat.lower()} priority in windows, styling and outreach this week.",
            "entities": [{
                "type": "product", "id": p["sku"], "name": p["product_name"],
                "detail": f"{p.get('stock')} in stock", "value": p.get("stock_value"),
            } for p in sorted(in_stock, key=lambda p: -(p.get("stock_value") or 0))[:8]],
            "product_skus": [p["sku"] for p in in_stock],
        })
    return out


def _size_gaps(profiles, products, value_scale) -> list[dict]:
    """Customers whose size is systematically missing from what we hold."""
    sized = [p for p in profiles if p.get("size_affinity")]
    if len(sized) < 5:
        return []
    stock_sizes = defaultdict(float)
    for p in products:
        if p.get("size") and (p.get("stock") or 0) > 0:
            stock_sizes[str(p["size"]).strip().upper()] += p["stock"]
    if not stock_sizes:
        return []
    total_stock = sum(stock_sizes.values())

    demand = defaultdict(float)
    for p in sized:
        top_size = next(iter(p["size_affinity"]))
        demand[str(top_size).strip().upper()] += p.get("total_spend") or 0
    total_demand = sum(demand.values()) or 1

    gaps = []
    for size, spend in sorted(demand.items(), key=lambda kv: -kv[1])[:6]:
        demand_share = spend / total_demand
        stock_share = stock_sizes.get(size, 0) / total_stock
        if demand_share > 0.12 and stock_share < demand_share * 0.5:
            gaps.append((size, demand_share, stock_share, spend))
    if not gaps:
        return []

    size, dshare, sshare, spend = gaps[0]
    probability = _BASE_PROBABILITY["size_gap"]
    group = [p for p in sized
             if str(next(iter(p["size_affinity"]))).strip().upper() == size]
    baskets = [p.get("avg_order_value") for p in group if p.get("avg_order_value")]
    avg_basket = statistics.mean(baskets) if baskets else 0
    # A stock gap costs you missed baskets, not a share of lifetime spend.
    missed = avg_basket * len(group) * 0.12

    return [{
        "id": f"size-gap-{size}",
        "type": "size_gap",
        "title": f"Size {size} is under-stocked versus demand",
        "explanation": (
            f"Customers who buy size {size} account for {dshare:.0%} of tracked spend, but "
            f"size {size} is only {sshare:.0%} of units on hand. You are likely turning away "
            "your own best-matched clients."
        ),
        "impact": round(missed, 2),
        "impact_basis": f"12% of one average basket across the {len(group)} customers in this size",
        "probability": probability,
        "urgency": 0.5,
        "confidence": 0.6,
        "score": _score(probability, missed, 0.5, 0.6, value_scale * 2),
        "action": f"Weight size {size} more heavily in the next buy or reorder.",
        "entities": [],
    }]


def pipeline_defaults(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand headline opportunities into per-customer pipeline rows."""
    rows: list[dict[str, Any]] = []
    for opp in opportunities:
        for ent in opp.get("entities", []):
            if ent.get("type") != "customer":
                continue
            rows.append({
                "id": f"{opp['id']}::{ent['id']}",
                "opportunity_id": opp["id"],
                "opportunity_type": opp["type"],
                "customer_id": ent["id"],
                "customer_name": ent["name"],
                "reason": ent.get("detail"),
                "product": ent.get("suggested_product"),
                "match_pct": ent.get("match_pct"),
                "value": ent.get("value"),
                "contactable": ent.get("contactable", False),
                "priority": opp["score"],
                "status": "New",
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
            })
    rows.sort(key=lambda r: -r["priority"])
    return rows
