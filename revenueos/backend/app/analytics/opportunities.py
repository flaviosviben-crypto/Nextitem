"""The Opportunity Engine: turn metrics into ranked, explainable revenue actions.

An opportunity is scored as

    Opportunity Score = probability × value × urgency × confidence

normalised to 0-100. Every component is derived from computed metrics — there
is no hand-written "this looks promising" text anywhere in this module, and each
opportunity carries the components that produced its score so the UI can show
the arithmetic.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .matching import (
    MatchingContext,
    build_profile,
    score_customers_for_product,
    score_products_for_customer,
)

KIND_META = {
    "overdue_vip": {"label": "Overdue high-value customer", "icon": "crown"},
    "reactivation": {"label": "Reactivation", "icon": "rotate"},
    "new_arrival_match": {"label": "New arrival match", "icon": "sparkles"},
    "dead_stock_rescue": {"label": "Dead stock rescue", "icon": "package"},
    "cross_sell": {"label": "Cross-sell", "icon": "shuffle"},
    "high_potential": {"label": "Growth opportunity", "icon": "trending-up"},
    "brand_restock": {"label": "Preferred brand arrival", "icon": "tag"},
    "private_sale": {"label": "Private sale candidate", "icon": "ticket"},
}


@dataclass
class Opportunity:
    id: str
    kind: str
    title: str
    explanation: str
    action: str
    estimated_value: float | None
    probability: float
    urgency: float
    confidence: float
    score: float
    customer_ids: list[str] = field(default_factory=list)
    product_ids: list[str] = field(default_factory=list)
    customers: list[dict[str, Any]] = field(default_factory=list)
    products: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    match_pct: int | None = None

    def to_dict(self) -> dict[str, Any]:
        meta = KIND_META.get(self.kind, {"label": self.kind, "icon": "zap"})
        return {
            "id": self.id,
            "kind": self.kind,
            "kindLabel": meta["label"],
            "icon": meta["icon"],
            "title": self.title,
            "explanation": self.explanation,
            "action": self.action,
            "estimatedValue": round(self.estimated_value, 2) if self.estimated_value is not None else None,
            "probability": round(self.probability, 4),
            "urgency": round(self.urgency, 4),
            "confidence": round(self.confidence, 4),
            "score": round(self.score, 1),
            "matchPct": self.match_pct,
            "customerIds": self.customer_ids,
            "productIds": self.product_ids,
            "customers": self.customers,
            "products": self.products,
            "evidence": self.evidence,
        }


def _oid(*parts: Any) -> str:
    digest = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return f"opp_{digest[:12]}"


def _score(probability: float, value: float | None, urgency: float, confidence: float,
           value_reference: float) -> float:
    """Normalise the four components into 0-100.

    ``value_reference`` is the dataset's own scale (a high-percentile basket),
    so the same code ranks sensibly for a €150 AOV store and a €4,000 one.
    """
    if value is None or value <= 0:
        value_component = 0.35     # unknown value ≠ no value
    else:
        value_component = float(np.clip(np.log1p(value) / np.log1p(max(value_reference, 1)), 0.05, 1.4))
    raw = probability * value_component * (0.55 + 0.45 * urgency) * (0.6 + 0.4 * confidence)
    return float(np.clip(raw * 100 / 0.72, 0, 100))


def _confidence_value(label: str | None) -> float:
    return {"high": 0.95, "medium": 0.7, "low": 0.45, "very low": 0.25}.get(label or "", 0.5)


def _customer_card(row: pd.Series, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    card = {
        "customerId": str(row.get("customer_id")),
        "name": row.get("display_name"),
        "segment": row.get("segment"),
        "totalSpend": _num(row.get("total_spend")),
        "avgOrderValue": _num(row.get("avg_order_value")),
        "recencyDays": _num(row.get("recency_days")),
        "daysOverdue": _num(row.get("days_overdue")),
        "customerScore": _num(row.get("customer_score")),
        "churnRisk": _num(row.get("churn_risk")),
        "predictedValue": _num(row.get("predicted_12m_value")),
        "dataConfidence": row.get("data_confidence"),
    }
    if extra:
        card.update(extra)
    return card


def _product_card(row: pd.Series, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    card = {
        "productId": str(row.get("product_id")),
        "name": row.get("product_name"),
        "brand": row.get("brand"),
        "category": row.get("category"),
        "price": _num(row.get("price")),
        "stock": _num(row.get("stock")),
        "status": row.get("status"),
        "riskScore": _num(row.get("risk_score")),
        "daysInStock": _num(row.get("days_in_stock")),
        "retailValue": _num(row.get("retail_value")),
    }
    if extra:
        card.update(extra)
    return card


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(number) or np.isinf(number):
        return None
    return round(number, 2)


# --------------------------------------------------------------------------- #
def generate_opportunities(
    customers: pd.DataFrame,
    products: pd.DataFrame,
    ctx: MatchingContext,
    transactions: pd.DataFrame | None = None,
    limit: int = 60,
    per_customer_products: int = 3,
) -> list[dict[str, Any]]:
    """Discover, score and rank every commercial opportunity in the dataset."""
    if customers is None or customers.empty:
        return []

    aov_series = customers["avg_order_value"].dropna() if "avg_order_value" in customers else pd.Series(dtype=float)
    value_reference = float(aov_series.quantile(0.85)) if not aov_series.empty else 500.0
    typical_basket = float(aov_series.median()) if not aov_series.empty else None

    opportunities: list[Opportunity] = []
    has_products = products is not None and not products.empty

    opportunities += _overdue_customers(customers, products, ctx, value_reference,
                                        typical_basket, per_customer_products, has_products)
    opportunities += _high_potential(customers, products, ctx, value_reference,
                                     typical_basket, has_products)
    if has_products:
        opportunities += _new_arrivals(customers, products, ctx, value_reference)
        opportunities += _dead_stock_rescue(customers, products, ctx, value_reference)
        opportunities += _brand_arrivals(customers, products, ctx, value_reference)
    opportunities += _private_sale(customers, value_reference, typical_basket)

    opportunities.sort(key=lambda o: o.score, reverse=True)
    return [o.to_dict() for o in opportunities[:limit]]


# --------------------------------------------------------------------------- #
def _overdue_customers(customers, products, ctx, value_reference, typical_basket,
                       per_customer_products, has_products) -> list[Opportunity]:
    if "days_overdue" not in customers.columns:
        return []
    pool = customers[
        customers["days_overdue"].notna()
        & (customers["days_overdue"] > 0)
        & (~customers["segment"].isin(["Lost"]) if "segment" in customers else True)
    ].copy()
    if pool.empty:
        return []

    pool["_priority"] = (
        pool["customer_score"].fillna(40) / 100 * 0.6
        + np.clip(pool["cycles_overdue"].fillna(0.2), 0, 2) / 2 * 0.4
    )
    pool = pool.sort_values("_priority", ascending=False).head(40)

    out: list[Opportunity] = []
    for _, row in pool.iterrows():
        overdue_days = float(row["days_overdue"])
        cycles = float(row["cycles_overdue"]) if pd.notna(row.get("cycles_overdue")) else 0.3
        basket = _num(row.get("avg_order_value")) or typical_basket
        churn = float(row["churn_risk"]) if pd.notna(row.get("churn_risk")) else 0.5

        # Probability of winning the sale from a *personal* contact. Falls as
        # they drift further past their window.
        probability = float(np.clip(0.42 * np.exp(-0.55 * max(cycles - 0.2, 0)), 0.05, 0.45))
        urgency = float(np.clip(cycles / 1.6, 0.15, 1.0))
        confidence = _confidence_value(row.get("data_confidence"))

        matches: list[dict[str, Any]] = []
        if has_products:
            profile = build_profile(row)
            matches = score_products_for_customer(profile, ctx, limit=per_customer_products)

        segment = row.get("segment") or "Customer"
        kind = "overdue_vip" if segment in {"Champions", "VIP", "Loyal"} else "reactivation"
        name = row.get("display_name") or row.get("customer_id")

        explanation_parts = [
            f"{name} normally buys every {int(row['expected_cycle_days'])} days and is "
            f"{int(overdue_days)} days past that window."
        ]
        if _num(row.get("total_spend")):
            explanation_parts.append(f"Lifetime spend €{_num(row.get('total_spend')):,.0f}.")
        if churn >= 0.6:
            explanation_parts.append(f"Churn risk is {churn:.0%} and rising.")
        if matches:
            top = matches[0]
            explanation_parts.append(
                f"Best current fit: {top['productName']} ({top['scorePct']}% match)."
            )

        action = (
            f"Call or message {name} with {matches[0]['productName']}"
            if matches else f"Contact {name} personally this week"
        )

        out.append(Opportunity(
            id=_oid("overdue", row["customer_id"]),
            kind=kind,
            title=f"{name} is {int(overdue_days)} days overdue",
            explanation=" ".join(explanation_parts),
            action=action,
            estimated_value=basket,
            probability=probability,
            urgency=urgency,
            confidence=confidence,
            score=_score(probability, basket, urgency, confidence, value_reference),
            customer_ids=[str(row["customer_id"])],
            product_ids=[m["productId"] for m in matches],
            customers=[_customer_card(row)],
            products=matches,
            match_pct=matches[0]["scorePct"] if matches else None,
            evidence=[
                {"label": "Expected cycle", "value": f"{int(row['expected_cycle_days'])} days"},
                {"label": "Days overdue", "value": f"{int(overdue_days)}"},
                {"label": "Segment", "value": str(segment)},
                {"label": "Churn risk", "value": f"{churn:.0%}"},
            ],
        ))
    return out


def _high_potential(customers, products, ctx, value_reference, typical_basket,
                    has_products) -> list[Opportunity]:
    if "segment" not in customers.columns:
        return []
    pool = customers[customers["segment"].isin(["High Potential", "Promising"])].copy()
    if pool.empty:
        return []
    pool = pool.sort_values("customer_score", ascending=False).head(15)

    out: list[Opportunity] = []
    for _, row in pool.iterrows():
        basket = _num(row.get("avg_order_value")) or typical_basket
        upside = _num(row.get("predicted_12m_value"))
        probability = 0.30
        urgency = 0.45
        confidence = _confidence_value(row.get("data_confidence"))
        matches = []
        if has_products:
            matches = score_products_for_customer(build_profile(row), ctx, limit=3)

        name = row.get("display_name") or row.get("customer_id")
        detail = (
            f"{name} is spending above average for how long they have been a customer"
            + (f", with an estimated €{upside:,.0f} of value over the next 12 months." if upside
               else ".")
        )
        out.append(Opportunity(
            id=_oid("potential", row["customer_id"]),
            kind="high_potential",
            title=f"Grow {name} into a top client",
            explanation=detail + (
                f" Their strongest current fit is {matches[0]['productName']} "
                f"({matches[0]['scorePct']}% match)." if matches else ""
            ),
            action=f"Invite {name} to a styling appointment with a curated selection",
            estimated_value=basket,
            probability=probability,
            urgency=urgency,
            confidence=confidence,
            score=_score(probability, basket, urgency, confidence, value_reference),
            customer_ids=[str(row["customer_id"])],
            product_ids=[m["productId"] for m in matches],
            customers=[_customer_card(row)],
            products=matches,
            match_pct=matches[0]["scorePct"] if matches else None,
            evidence=[
                {"label": "Segment", "value": str(row.get("segment"))},
                {"label": "Customer score", "value": f"{_num(row.get('customer_score'))}/100"},
                {"label": "Predicted 12m value",
                 "value": f"€{upside:,.0f}" if upside else "Not enough information"},
            ],
        ))
    return out


def _new_arrivals(customers, products, ctx, value_reference) -> list[Opportunity]:
    if "days_in_stock" not in products.columns:
        return []
    fresh = products[
        products["days_in_stock"].notna()
        & (products["days_in_stock"] <= 45)
        & (products["stock"].fillna(1) > 0)
    ].copy()
    if fresh.empty:
        return []
    if "retail_value" in fresh.columns:
        fresh = fresh.sort_values("retail_value", ascending=False)
    fresh = fresh.head(12)

    out: list[Opportunity] = []
    for _, product in fresh.iterrows():
        matches = score_customers_for_product(product, customers, ctx, limit=12, min_score=0.55)
        if len(matches) < 2:
            continue
        price = _num(product.get("price"))
        strong = [m for m in matches if m["scorePct"] >= 70]
        probability = float(np.clip(0.16 + 0.02 * len(strong), 0.12, 0.42))
        potential = (price or value_reference) * max(len(strong), 1) * probability
        confidence = float(np.mean([_confidence_value(m["dataConfidence"]) for m in matches]))
        urgency = 0.7

        name = product.get("product_name")
        out.append(Opportunity(
            id=_oid("arrival", product["product_id"]),
            kind="new_arrival_match",
            title=f"{len(matches)} customers match the new {name}",
            explanation=(
                f"{name}"
                + (f" ({product.get('brand')})" if product.get("brand") else "")
                + (f" at €{price:,.0f}" if price else "")
                + f" arrived {int(float(product['days_in_stock']))} days ago. "
                f"{len(strong)} customer(s) score above 70% on category, price and size fit."
            ),
            action=f"Contact the top {min(len(matches), 8)} matches before the piece sells through",
            estimated_value=potential,
            probability=probability,
            urgency=urgency,
            confidence=confidence,
            score=_score(probability, potential, urgency, confidence, value_reference),
            customer_ids=[m["customerId"] for m in matches],
            product_ids=[str(product["product_id"])],
            customers=matches,
            products=[_product_card(product)],
            match_pct=matches[0]["scorePct"],
            evidence=[
                {"label": "Days in stock", "value": f"{int(float(product['days_in_stock']))}"},
                {"label": "Strong matches (≥70%)", "value": str(len(strong))},
                {"label": "Units on hand", "value": f"{_num(product.get('stock')) or '—'}"},
            ],
        ))
    return out


def _dead_stock_rescue(customers, products, ctx, value_reference) -> list[Opportunity]:
    if "status" not in products.columns:
        return []
    stuck = products[
        products["status"].isin(["At Risk", "Dead Stock"])
        & (products["stock"].fillna(0) > 0)
    ].copy()
    if stuck.empty:
        return []
    if "retail_value" in stuck.columns:
        stuck = stuck.sort_values("retail_value", ascending=False)
    stuck = stuck.head(12)

    out: list[Opportunity] = []
    for _, product in stuck.iterrows():
        matches = score_customers_for_product(product, customers, ctx, limit=15, min_score=0.5)
        value = _num(product.get("retail_value")) or _num(product.get("price"))
        price = _num(product.get("price"))
        strong = [m for m in matches if m["scorePct"] >= 65]
        probability = float(np.clip(0.10 + 0.022 * len(strong), 0.08, 0.38))
        confidence = (
            float(np.mean([_confidence_value(m["dataConfidence"]) for m in matches]))
            if matches else 0.35
        )
        risk = _num(product.get("risk_score")) or 60
        urgency = float(np.clip(risk / 100, 0.3, 1.0))
        recovery = (price or value_reference) * max(len(strong), 1) * probability

        name = product.get("product_name")
        days = product.get("days_in_stock")
        detail = [f"{name} carries a risk score of {risk:.0f}/100"]
        if days is not None and pd.notna(days):
            detail.append(f"{int(float(days))} days in stock")
        if value:
            detail.append(f"€{value:,.0f} of stock value tied up")
        detail.append(
            f"{len(strong)} customer(s) have a genuine affinity for it"
            if strong else "no strong customer affinity was found"
        )

        action = (
            f"Target the top {min(len(matches), 10)} matched customers before applying any discount"
            if strong else
            "Customer affinity is weak — this is the one to consider for a markdown or a bundle"
        )

        out.append(Opportunity(
            id=_oid("rescue", product["product_id"]),
            kind="dead_stock_rescue",
            title=f"Rescue {name} before discounting",
            explanation=", ".join(detail) + ".",
            action=action,
            estimated_value=recovery,
            probability=probability,
            urgency=urgency,
            confidence=confidence,
            score=_score(probability, recovery, urgency, confidence, value_reference),
            customer_ids=[m["customerId"] for m in matches],
            product_ids=[str(product["product_id"])],
            customers=matches,
            products=[_product_card(product)],
            match_pct=matches[0]["scorePct"] if matches else None,
            evidence=[
                {"label": "Risk score", "value": f"{risk:.0f}/100"},
                {"label": "Stock value", "value": f"€{value:,.0f}" if value else "Not enough information"},
                {"label": "Matched customers (≥65%)", "value": str(len(strong))},
            ],
        ))
    return out


def _brand_arrivals(customers, products, ctx, value_reference) -> list[Opportunity]:
    """Customers who repeatedly buy a brand that has fresh stock in the catalogue."""
    if "brand" not in products.columns or "brand_affinity" not in customers.columns:
        return []
    in_stock = products[(products["stock"].fillna(1) > 0) & products["brand"].notna()]
    if in_stock.empty:
        return []
    available_brands = {str(b).strip().lower() for b in in_stock["brand"].dropna()}

    loyalists: dict[str, list[pd.Series]] = {}
    for _, row in customers.iterrows():
        affinity = row.get("brand_affinity")
        if not isinstance(affinity, list) or not affinity:
            continue
        top = affinity[0]
        brand = str(top.get("value", "")).strip().lower()
        share = float(top.get("share") or 0)
        if brand in available_brands and share >= 0.4:
            loyalists.setdefault(brand, []).append(row)

    out: list[Opportunity] = []
    for brand, rows in sorted(loyalists.items(), key=lambda kv: -len(kv[1])):
        if len(rows) < 3:
            continue
        brand_products = in_stock[in_stock["brand"].astype(str).str.lower() == brand]
        if brand_products.empty:
            continue
        display_brand = str(brand_products.iloc[0]["brand"])
        baskets = [_num(r.get("avg_order_value")) for r in rows]
        baskets = [b for b in baskets if b]
        avg_basket = float(np.mean(baskets)) if baskets else value_reference
        probability = 0.24
        urgency = 0.5
        confidence = float(np.mean([_confidence_value(r.get("data_confidence")) for r in rows]))
        potential = avg_basket * len(rows) * probability

        out.append(Opportunity(
            id=_oid("brand", brand),
            kind="brand_restock",
            title=f"{len(rows)} loyal {display_brand} buyers, {len(brand_products)} pieces in stock",
            explanation=(
                f"These customers put at least 40% of their spend into {display_brand}. "
                f"You currently hold {len(brand_products)} {display_brand} SKU(s) in stock."
            ),
            action=f"Send a {display_brand} arrivals preview to this group",
            estimated_value=potential,
            probability=probability,
            urgency=urgency,
            confidence=confidence,
            score=_score(probability, potential, urgency, confidence, value_reference),
            customer_ids=[str(r["customer_id"]) for r in rows],
            product_ids=[str(p) for p in brand_products["product_id"].astype(str).head(8)],
            customers=[_customer_card(r) for r in rows[:12]],
            products=[_product_card(p) for _, p in brand_products.head(6).iterrows()],
            evidence=[
                {"label": "Loyal customers", "value": str(len(rows))},
                {"label": "SKUs in stock", "value": str(len(brand_products))},
                {"label": "Avg basket", "value": f"€{avg_basket:,.0f}"},
            ],
        ))
    return out[:6]


def _private_sale(customers, value_reference, typical_basket) -> list[Opportunity]:
    if "segment" not in customers.columns:
        return []
    pool = customers[customers["segment"].isin(["Discount Driven", "Sleeping", "At Risk"])]
    if len(pool) < 5:
        return []
    baskets = pool["avg_order_value"].dropna()
    avg_basket = float(baskets.mean()) if not baskets.empty else (typical_basket or value_reference)
    probability = 0.18
    potential = avg_basket * len(pool) * probability
    confidence = float(np.mean([_confidence_value(v) for v in pool.get("data_confidence", [])])) \
        if "data_confidence" in pool.columns else 0.5

    return [Opportunity(
        id=_oid("private_sale", len(pool)),
        kind="private_sale",
        title=f"Private sale audience of {len(pool)} customers",
        explanation=(
            f"{len(pool)} customers are either discount-driven, drifting or sleeping. "
            f"Their average basket is €{avg_basket:,.0f}. A closed-door event converts this "
            "group without discounting to your full-price clientèle."
        ),
        action="Build a private sale campaign for this audience",
        estimated_value=potential,
        probability=probability,
        urgency=0.4,
        confidence=confidence,
        score=_score(probability, potential, 0.4, confidence, value_reference),
        customer_ids=[str(c) for c in pool["customer_id"].astype(str).tolist()],
        customers=[_customer_card(r) for _, r in pool.head(20).iterrows()],
        evidence=[
            {"label": "Audience size", "value": str(len(pool))},
            {"label": "Avg basket", "value": f"€{avg_basket:,.0f}"},
            {"label": "Assumed conversion", "value": f"{probability:.0%}"},
        ],
    )]


def opportunity_totals(opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    """Headline numbers for the dashboard, expected-value weighted."""
    if not opportunities:
        return {"count": 0, "totalValue": None, "expectedValue": None, "byKind": {}}

    values = [o["estimatedValue"] for o in opportunities if o.get("estimatedValue")]
    expected = [
        o["estimatedValue"] * o["probability"]
        for o in opportunities if o.get("estimatedValue")
    ]
    by_kind: dict[str, dict[str, Any]] = {}
    for opp in opportunities:
        entry = by_kind.setdefault(opp["kind"], {"count": 0, "value": 0.0,
                                                 "label": opp["kindLabel"]})
        entry["count"] += 1
        entry["value"] += opp.get("estimatedValue") or 0.0

    customers = {c for o in opportunities for c in o.get("customerIds", [])}
    products = {p for o in opportunities for p in o.get("productIds", [])}
    return {
        "count": len(opportunities),
        "totalValue": round(sum(values), 2) if values else None,
        "expectedValue": round(sum(expected), 2) if expected else None,
        "customersInvolved": len(customers),
        "productsInvolved": len(products),
        "byKind": {k: {**v, "value": round(v["value"], 2)} for k, v in by_kind.items()},
    }
