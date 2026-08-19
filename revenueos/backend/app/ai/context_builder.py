"""Build minimised context for the model, plus deterministic fallbacks.

Two responsibilities:

1. **Privacy minimisation** — GDPR-minded. Only the fields an analysis genuinely
   needs leave the server. Email, phone, address and birth date are stripped
   before anything reaches the API.
2. **Deterministic narratives** — when no API key is configured, RevenueOS still
   describes each customer and the week's performance, using computed metrics
   only. These are labelled ``engine: "computed"`` so nothing masquerades as
   model reasoning.
"""
from __future__ import annotations

from typing import Any

_PII_FIELDS = {"email", "phone", "address", "birth_date", "notes", "postcode", "street"}


def minimise(record: dict[str, Any]) -> dict[str, Any]:
    """Drop direct identifiers before a record is sent to the model."""
    return {k: v for k, v in record.items()
            if k not in _PII_FIELDS and not k.startswith("_")}


def customer_context(profile: dict[str, Any], matches: list[dict[str, Any]],
                     recent: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "customer": minimise({
            "name": profile.get("name"),
            "value_tier": profile.get("value_tier"),
            "lifecycle": profile.get("lifecycle"),
            "customer_score": profile.get("customer_score"),
            "total_spend": profile.get("total_spend"),
            "spend_source": profile.get("spend_source"),
            "orders": profile.get("order_count"),
            "avg_order_value": profile.get("avg_order_value"),
            "first_purchase": profile.get("first_purchase"),
            "last_purchase": profile.get("last_purchase"),
            "days_since_purchase": profile.get("recency_days"),
            "typical_cycle_days": profile.get("cycle_days"),
            "cycle_confidence": profile.get("cycle_confidence"),
            "cycle_position": profile.get("cycle_position"),
            "purchases_per_year": profile.get("frequency_per_year"),
            "spend_growth": profile.get("spend_growth"),
            "category_affinity": profile.get("category_affinity"),
            "brand_affinity": profile.get("brand_affinity"),
            "color_affinity": profile.get("color_affinity"),
            "size_affinity": profile.get("size_affinity"),
            "price_band": [profile.get("price_low"), profile.get("price_high")],
            "discount_share": profile.get("discount_share"),
            "store": profile.get("store"),
            "contactable": profile.get("contactable", False),
            "data_confidence": profile.get("data_confidence"),
        }),
        "recommended_products": [{
            "product": m["product_name"], "price": m["price"],
            "match_pct": m["match_pct"], "why": m["why"], "caveats": m["caveats"],
        } for m in matches[:3]],
        "recent_purchases": [{
            "date": str(t.get("date")), "product": t.get("product"),
            "category": t.get("category"), "brand": t.get("brand"),
            "amount": t.get("line_total"),
        } for t in recent[:8]],
    }


# ------------------------------------------------------- deterministic text --

def _eur(value: float | None) -> str:
    return f"€{value:,.0f}" if value else "—"


def _days(value: int | None) -> str:
    """'1 day', not '1 days'."""
    if value is None:
        return "—"
    return "1 day" if value == 1 else f"{value} days"


def _segment_phrase(segment: str) -> str:
    """Keep acronyms upper-case: 'a VIP customer', not 'a vip customer'."""
    if segment.isupper() or segment in {"VIP", "VIC"}:
        return f"a {segment}"
    return f"a {segment.lower()}"


def describe_customer(profile: dict[str, Any], matches: list[dict[str, Any]]) -> str:
    """A factual profile sentence built purely from computed metrics."""
    name = (profile.get("name") or "This customer").split()[0]
    bits: list[str] = []

    tier = profile.get("value_tier")
    stage = profile.get("lifecycle")
    spend = profile.get("total_spend")
    orders = profile.get("order_count")
    if tier:
        opener = f"{name} is {_segment_phrase(tier)} customer"
        if stage:
            opener += f", currently {stage.lower()} in their buying cycle"
        if spend:
            opener += f" with {_eur(spend)} of recorded spend"
            if orders:
                opener += f" across {orders} order{'s' if orders != 1 else ''}"
        bits.append(opener + ".")
    elif spend:
        bits.append(f"{name} has spent {_eur(spend)} to date.")
    else:
        bits.append(f"{name} has no recorded spend yet.")

    cycle = profile.get("cycle_days")
    recency = profile.get("recency_days")
    position = profile.get("cycle_position")
    # Say how sure we are of the cycle in the same breath as the cycle itself,
    # so a number inferred from a cohort never reads as this customer's own habit.
    hedge = {"High": "", "Medium": " (estimated)",
             "Low": " (inferred from similar customers)"}.get(
        profile.get("cycle_confidence") or "", "")
    if cycle and recency is not None and position:
        bits.append(f"They buy roughly every {cycle:.0f} days{hedge}; their last purchase "
                    f"was {_days(recency)} ago — {position:.0%} through that cycle.")
    elif recency is not None:
        bits.append(f"Their last purchase was {_days(recency)} ago.")

    cat = profile.get("top_category")
    share = profile.get("top_category_share")
    brand = profile.get("top_brand")
    low, high = profile.get("price_low"), profile.get("price_high")
    taste: list[str] = []
    if cat:
        taste.append(f"{cat}" + (f" ({share:.0%} of spend)" if share else ""))
    if brand:
        taste.append(f"favours {brand}")
    if low and high:
        taste.append(f"typically spends {_eur(low)}–{_eur(high)} per piece")
    if taste:
        bits.append("They concentrate on " + ", ".join(taste) + ".")

    if matches:
        top = matches[0]
        bits.append(f"Best current match: {top['product_name']} at {top['match_pct']}%.")

    elig = profile.get("eligibility") or {}
    if elig.get("status") == "Suppressed":
        bits.append(f"Outreach is blocked: {elig.get('reason')}")
    elif profile.get("contact_channels"):
        bits.append("Permitted channels: " + ", ".join(profile["contact_channels"]) + ".")

    return " ".join(bits)


def describe_actions(profile: dict[str, Any], matches: list[dict[str, Any]]) -> list[str]:
    """Next best actions derived from the metrics, without a model."""
    actions: list[str] = []
    elig = profile.get("eligibility") or {}
    if elig.get("status") == "Suppressed":
        # Nothing below this line may suggest reaching out. A suppressed customer
        # gets one honest instruction, not a list of contradictory ones.
        return [f"Do not contact. {elig.get('reason') or 'No permitted channel on file.'}"]

    # Timing comes from the lifecycle stage alone, so the advice can never
    # disagree with the badge the advisor is looking at.
    stage = profile.get("lifecycle")
    cycle = profile.get("cycle_days")
    against = f" against their {cycle:.0f}-day cycle" if cycle else ""
    if stage == "Due":
        actions.append(f"Contact this week — they are at their repurchase point{against}.")
    elif stage == "At Risk":
        actions.append(f"Contact now — they have drifted past their usual rhythm{against}.")
    elif stage == "Lost":
        actions.append("Win-back conversation — they need a real reason to return, "
                       "not a routine follow-up.")
    else:
        actions.append("No need to chase — they are inside their normal buying rhythm.")

    if matches:
        top = matches[0]
        price = f" ({_eur(top['price'])})" if top.get("price") else ""
        actions.append(f"Recommend {top['product_name']}{price} — {top['match_pct']}% match.")
        if len(matches) > 1:
            actions.append(f"Hold {matches[1]['product_name']} as a second option.")

    if (profile.get("discount_share") or 0) < 0.2 and profile.get("total_spend"):
        actions.append("Avoid discounting — they buy at full price.")
    elif (profile.get("discount_share") or 0) >= 0.6:
        actions.append("Time outreach to the sale cycle; they buy on promotion.")

    if profile.get("value_tier") == "VIP":
        actions.append("Invite to the next private preview.")

    return actions[:4] or ["Not enough history yet — capture more purchase detail."]


def describe_week(summary: dict[str, Any], trend: list[dict[str, Any]],
                  opportunities: list[dict[str, Any]], quality: dict[str, Any]) -> str:
    """A computed weekly briefing, used when no model is configured."""
    lines: list[str] = []
    customers = summary.get("customers", {})
    inventory = summary.get("inventory", {})

    if len(trend) >= 2:
        latest, prior = trend[-1], trend[-2]
        if prior["revenue"]:
            delta = (latest["revenue"] - prior["revenue"]) / prior["revenue"]
            lines.append(
                f"Wins. {latest['month']} revenue is {_eur(latest['revenue'])} across "
                f"{latest['orders']} orders, {delta:+.1%} versus {prior['month']}.")
        else:
            lines.append(f"Wins. {latest['month']} revenue is {_eur(latest['revenue'])}.")
    elif customers.get("total_spend"):
        lines.append(f"Wins. Recorded customer spend totals {_eur(customers['total_spend'])}.")

    risks = []
    if customers.get("overdue_customers"):
        risks.append(f"{customers['overdue_customers']} customers are past their normal "
                     "repurchase window")
    if inventory.get("at_risk_value"):
        risks.append(f"{_eur(inventory['at_risk_value'])} of stock is ageing or dead")
    if risks:
        lines.append("Risks. " + "; ".join(risks) + ".")

    if opportunities:
        top = opportunities[0]
        total = sum(o.get("impact") or 0 for o in opportunities)
        lines.append(f"Opportunities. {len(opportunities)} plays are open, worth an estimated "
                     f"{_eur(total)}. The largest is: {top['title'].lower()}.")

    if opportunities:
        lines.append("Recommended actions. " + opportunities[0]["action"])
    elif quality.get("score", 100) < 60:
        lines.append("Recommended actions. Improve the imported data — "
                     + (quality.get("summary") or ""))

    return " ".join(lines) or "Not enough data yet to summarise the week."
