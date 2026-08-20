"""Today's Opportunities: one customer, one reason, one thing to do.

This is the product. Everything else in RevenueOS exists to make this list
correct. An advisor with 500 clients opens one screen and sees the handful worth
a conversation today, each answering five questions in order:

    Who      — the customer
    Why now  — the trigger, stated as evidence, not as a score
    What     — the product to put in front of them
    Why that — the signals behind the recommendation
    How      — the channel they have actually agreed to

Two rules govern the list.

**Never pad.** The list is as long as the evidence supports. If seven customers
deserve a call today, the advisor sees seven. A quota would train them to
distrust the whole screen.

**Lifecycle does not set priority.** A VIP who is Lost can outrank a Standard
customer who is Due. Value, timing, product fit and reachability are combined;
no single dimension wins on its own.
"""
from __future__ import annotations

import statistics
from datetime import date, datetime
from typing import Any

from . import compliance, matching

# Conservative conversion priors by trigger, from published retail response
# rates rather than from this boutique's own history — which we do not have
# until outcomes accumulate. They are stated in the UI as modelled, not measured.
TRIGGER_PRIORS = {
    "due": 0.30,
    "at_risk": 0.18,
    "win_back": 0.09,
    "new_arrival": 0.22,
    "cross_sell": 0.16,
    "restock_affinity": 0.15,
}

# How much of a matched customer's response we are willing to call *incremental*
# — i.e. revenue that would not have arrived anyway. Deliberately harsh: a Due
# customer was already likely to come back on their own.
INCREMENTALITY = {
    "due": 0.35,
    "at_risk": 0.60,
    "win_back": 0.85,
    "new_arrival": 0.45,
    "cross_sell": 0.55,
    "restock_affinity": 0.50,
}

# Below this the recommendation is not credible enough to put in front of an
# advisor. Showing a weak match costs more trust than showing nothing.
MIN_MATCH_SCORE = 0.45
MIN_PRIORITY = 35

_CONFIDENCE_VALUE = {"High": 1.0, "Medium": 0.8, "Low": 0.55, "None": 0.4}


def _plural_days(value: int | None) -> str:
    if value is None:
        return "recently"
    return "1 day" if value == 1 else f"{value} days"


# ----------------------------------------------------------------- triggers ---

def _lifecycle_trigger(profile: dict[str, Any]) -> dict[str, Any] | None:
    """The customer's own buying rhythm says it is time."""
    stage = profile.get("lifecycle")
    if stage not in {"Due", "At Risk", "Lost"}:
        return None

    recency = profile.get("recency_days")
    position = profile.get("cycle_position")
    cycle = profile.get("cycle_days")
    confidence = profile.get("cycle_confidence") or "Low"

    if stage == "Due":
        kind, headline = "due", "Due for their next purchase"
    elif stage == "At Risk":
        kind, headline = "at_risk", "Drifting past their usual rhythm"
    else:
        kind, headline = "win_back", "Lapsed — worth a genuine win-back"

    if cycle and position:
        # Say what we saw, and say how sure we are of the cycle behind it.
        qualifier = {"High": "", "Medium": " (estimated cycle)",
                     "Low": " (cycle inferred from similar customers)"}.get(confidence, "")
        why = (f"Last bought {_plural_days(recency)} ago against a {round(cycle)}-day "
               f"buying cycle{qualifier}.")
    else:
        why = f"Last bought {_plural_days(recency)} ago."

    return {"kind": kind, "headline": headline, "why_now": why,
            "evidence": profile.get("lifecycle_basis")}


def _new_arrival_trigger(profile: dict[str, Any], match: dict[str, Any] | None,
                         product_index: dict[str, dict]) -> dict[str, Any] | None:
    """Something just landed that this customer specifically would want."""
    if not match:
        return None
    product = product_index.get(str(match.get("sku")))
    age = (product or {}).get("days_in_stock")
    if age is None or age > 45 or match["score"] < 0.6:
        return None
    return {
        "kind": "new_arrival",
        "headline": "New arrival matches them closely",
        "why_now": (f"{match['product_name']} arrived {_plural_days(age)} ago and matches "
                    f"their buying profile at {match['match_pct']}%."),
        "evidence": "; ".join(match.get("why", [])[:2]) or None,
    }


def _cross_sell_trigger(profile: dict[str, Any], match: dict[str, Any] | None
                        ) -> dict[str, Any] | None:
    """A proven repeat customer who has only ever bought one category."""
    affinity = profile.get("category_affinity") or {}
    orders = profile.get("order_count") or 0
    if len(affinity) != 1 or orders < 3 or not match:
        return None
    owned = next(iter(affinity))
    if not match.get("category") or match["category"] == owned:
        return None
    return {
        "kind": "cross_sell",
        "headline": f"Buys only {owned} — room to widen",
        "why_now": (f"{orders} purchases, all in {owned}. {match['product_name']} is the "
                    f"natural first step into {match['category']}."),
        "evidence": "; ".join(match.get("why", [])[:2]) or None,
    }


def _restock_trigger(profile: dict[str, Any], match: dict[str, Any] | None,
                     product_index: dict[str, dict]) -> dict[str, Any] | None:
    """Stock that is not moving, in front of the person most likely to want it."""
    if not match or match["score"] < 0.6:
        return None
    product = product_index.get(str(match.get("sku")))
    if not product or product.get("risk_class") not in {"At Risk", "Dead Stock"}:
        return None
    return {
        "kind": "restock_affinity",
        "headline": "Strong match for stock that needs to move",
        "why_now": (f"{match['product_name']} has been sitting "
                    f"{_plural_days(product.get('days_in_stock'))} and this customer matches "
                    f"it at {match['match_pct']}% — a personal offer before any markdown."),
        "evidence": "; ".join(match.get("why", [])[:2]) or None,
    }


# ---------------------------------------------------------------- scoring ---

def _probability(trigger_kind: str, profile: dict[str, Any],
                 match: dict[str, Any] | None) -> float:
    """Modelled likelihood this contact converts. Never presented as measured."""
    p = TRIGGER_PRIORS.get(trigger_kind, 0.15)

    # A strong product match lifts the odds; a weak one does not rescue them.
    if match:
        p *= 0.8 + 0.4 * min(1.0, match["score"])

    # Established relationships answer more often than new ones.
    if (profile.get("order_count") or 0) >= 4:
        p *= 1.15
    elif (profile.get("order_count") or 0) <= 1:
        p *= 0.8

    return round(min(0.6, p), 3)


def _basket(profile: dict[str, Any], match: dict[str, Any] | None) -> float | None:
    """What one successful conversation is plausibly worth."""
    price = (match or {}).get("price")
    aov = profile.get("avg_order_value")
    if price and aov:
        # Neither number alone is right: the recommended piece anchors it, the
        # customer's own history keeps it honest.
        return round((price + aov) / 2, 2)
    return price or aov


def _priority(profile: dict[str, Any], trigger: dict[str, Any], probability: float,
              incremental: float | None, match: dict[str, Any] | None,
              value_scale: float, eligible: bool) -> int:
    """Blend the dimensions that actually decide who to call first.

    Lifecycle contributes urgency, never rank on its own — which is why a VIP who
    lapsed can still sit at the top of the list.
    """
    value = min(1.0, (profile.get("value_percentile") or 0.3))
    tier_boost = {"VIP": 0.15, "Promising": 0.07}.get(profile.get("value_tier"), 0.0)
    value = min(1.0, value + tier_boost)

    urgency = {"due": 1.0, "at_risk": 0.8, "new_arrival": 0.75,
               "restock_affinity": 0.6, "cross_sell": 0.45, "win_back": 0.5}.get(
        trigger["kind"], 0.5)

    money = min(1.0, (incremental or 0) / value_scale) if value_scale > 0 else 0.3
    fit = match["score"] if match else 0.35
    conf = _CONFIDENCE_VALUE.get(profile.get("data_confidence", "Medium"), 0.7)
    cycle_conf = _CONFIDENCE_VALUE.get(profile.get("cycle_confidence", "Low"), 0.55)

    raw = (0.26 * value
           + 0.20 * urgency
           + 0.18 * money
           + 0.16 * fit
           + 0.10 * min(1.0, probability / 0.35)
           + 0.10 * (0.5 * conf + 0.5 * cycle_conf))

    # An unreachable customer is still a real opportunity — it just cannot be
    # acted on today, so it never outranks one that can.
    if not eligible:
        raw *= 0.55

    return int(round(max(0, min(100, raw * 100))))


# ------------------------------------------------------------------ engine ---

def detect(
    profiles: list[dict[str, Any]],
    products: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    as_of: date | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """One opportunity per customer who genuinely warrants a conversation today.

    ``limit`` caps the list for display; it never pads it. A quiet day produces a
    short list, which is the honest answer.
    """
    if as_of is None:
        tx_dates = [t["date"] for t in transactions if t.get("date")]
        as_of = max(tx_dates) if tx_dates else date.today()

    product_index = {str(p["sku"]): p for p in products}

    baskets = [p["avg_order_value"] for p in profiles if p.get("avg_order_value")]
    value_scale = (statistics.median(baskets) if baskets else 500.0) or 500.0

    found: list[dict[str, Any]] = []
    for profile in profiles:
        opp = _for_customer(profile, products, product_index, value_scale, as_of)
        if opp:
            found.append(opp)

    found.sort(key=lambda o: -o["priority"])
    return found[:limit] if limit else found


def _for_customer(profile: dict[str, Any], products: list[dict[str, Any]],
                  product_index: dict[str, dict], value_scale: float,
                  as_of: date) -> dict[str, Any] | None:
    matches = matching.best_products_for_customer(
        profile, products, limit=3, min_score=MIN_MATCH_SCORE) if products else []
    best = matches[0] if matches else None

    # The strongest reason wins; a customer gets one card, not five.
    candidates = [
        _new_arrival_trigger(profile, best, product_index),
        _lifecycle_trigger(profile),
        _restock_trigger(profile, best, product_index),
        _cross_sell_trigger(profile, best),
    ]
    triggers = [t for t in candidates if t]
    if not triggers:
        return None

    order = ["due", "at_risk", "new_arrival", "win_back", "restock_affinity", "cross_sell"]
    trigger = min(triggers, key=lambda t: order.index(t["kind"]))

    # A win-back with nothing to offer is a cold call, not an opportunity.
    if trigger["kind"] == "win_back" and not best:
        return None

    probability = _probability(trigger["kind"], profile, best)
    basket = _basket(profile, best)
    influenced = round(basket * probability, 2) if basket else None
    incremental = (round(influenced * INCREMENTALITY[trigger["kind"]], 2)
                   if influenced else None)

    eligibility = profile.get("eligibility") or compliance.evaluate(profile, as_of)
    eligible = eligibility["status"] == "Actionable"
    priority = _priority(profile, trigger, probability, incremental, best,
                         value_scale, eligible)
    if priority < MIN_PRIORITY:
        return None

    return {
        "id": f"opp::{profile['customer_id']}::{trigger['kind']}",
        "customer_id": profile["customer_id"],
        "customer_name": profile.get("name"),
        "value_tier": profile.get("value_tier"),
        "lifecycle": profile.get("lifecycle"),
        "segment": profile.get("segment"),

        "trigger": trigger["kind"],
        "headline": trigger["headline"],
        "why_now": trigger["why_now"],
        "evidence": trigger.get("evidence"),

        "product": _product_card(best, product_index) if best else None,
        "alternatives": [_product_card(m, product_index) for m in matches[1:3]],

        "action": _action_text(trigger, eligibility, best),
        "eligibility": eligibility,
        "contactable": eligible,

        # Money, stated twice and labelled: what a conversation is worth, and how
        # much of it we are prepared to claim as caused by RevenueOS.
        "basket_value": basket,
        "influenced_value": influenced,
        "incremental_value": incremental,
        "value_basis": ("Recommended piece and this customer's own average basket, "
                        f"weighted by a modelled {probability:.0%} response rate"
                        if basket else "Not enough spending history to estimate"),
        "probability": probability,
        "probability_basis": "Modelled from retail response benchmarks, not measured here",

        # Kept for ranking and analysis; the card does not show them.
        "priority": priority,
        "data_confidence": profile.get("data_confidence"),
        "cycle_confidence": profile.get("cycle_confidence"),
        "created_at": as_of.isoformat(),
    }


def _product_card(match: dict[str, Any], product_index: dict[str, dict]) -> dict[str, Any]:
    """The product, plus the stock context that makes it safe to promise."""
    product = product_index.get(str(match.get("sku"))) or {}
    stock = product.get("stock")
    if stock is None:
        availability = "Stock not tracked"
    elif stock <= 2:
        availability = f"Only {int(stock)} left"
    else:
        availability = f"{int(stock)} in stock"

    return {
        "sku": match.get("sku"),
        "name": match.get("product_name"),
        "category": match.get("category"),
        "brand": match.get("brand"),
        "price": match.get("price"),
        "match_pct": match.get("match_pct"),
        "why": match.get("why", [])[:3],
        "caveats": match.get("caveats", [])[:2],
        "missing_signals": match.get("missing_signals", []),
        "match_confidence": match.get("data_confidence"),
        "availability": availability,
        "stock": stock,
        "risk_class": product.get("risk_class"),
    }


def _action_text(trigger: dict[str, Any], eligibility: dict[str, Any],
                 match: dict[str, Any] | None) -> str:
    """What to do — named only in a channel this customer has agreed to."""
    if eligibility["status"] != "Actionable":
        return f"Do not contact. {eligibility.get('reason') or ''}".strip()

    channel = eligibility.get("preferred_channel") or {}
    verb = channel.get("verb", "Reach out")
    piece = match["product_name"] if match else None

    if trigger["kind"] == "win_back":
        opener = "with a genuine reason to return"
    elif trigger["kind"] == "new_arrival":
        opener = "before the piece goes on the floor"
    elif trigger["kind"] == "cross_sell":
        opener = "and style it against what they already own"
    else:
        opener = "with a personal note"

    if piece:
        return f"{verb} about the {piece}, {opener}."
    return f"{verb} {opener}."


# Today's list is a workload, not a feed. Both numbers are real rules applied in
# the engine, not display truncation: an opportunity below the bar is not worth
# interrupting anyone over, and nobody makes fifty personal calls in a morning.
PRIORITY_BAR = 55
DAILY_CAP = 20


def prioritize(opportunities: list[dict[str, Any]], max_cards: int = DAILY_CAP,
               bar: int = PRIORITY_BAR) -> list[dict[str, Any]]:
    """Choose today's workload out of everything detected, and mark the choice.

    Called once per pipeline run. Every detected opportunity is stamped with
    ``prioritized_today``, so the decision travels with the object and each
    screen reads the same answer instead of recomputing its own. Two screens
    independently deciding what "today" means is how a product ends up quoting
    two different sizes for the same day's work.

    There is a ceiling but no floor: if only seven clear the bar the advisor sees
    seven, and can trust that the eighth genuinely was not worth their time.
    """
    eligible = [o for o in opportunities if o["priority"] >= bar and o["contactable"]]
    eligible.sort(key=lambda o: -o["priority"])
    chosen = eligible[:max_cards]
    chosen_ids = {id(o) for o in chosen}
    for opp in opportunities:
        opp["prioritized_today"] = id(opp) in chosen_ids
    return chosen


def todays_list(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read back the prioritized set. A lookup, never a second decision."""
    today = [o for o in opportunities if o.get("prioritized_today")]
    today.sort(key=lambda o: -o["priority"])
    return today


def decided_ids(pipeline: list[dict[str, Any]]) -> set[str]:
    """Recommendations an advisor has already ruled on."""
    return {r["id"] for r in pipeline
            if r.get("status") and r["status"] != "New"}


def awaiting_decision(opportunities: list[dict[str, Any]],
                      pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Today's recommendations that still need a decision — the inbox.

    A decision removes a recommendation from the queue but not from the day:
    it was still recommended, and Performance has to keep counting it.
    """
    settled = decided_ids(pipeline)
    return [o for o in todays_list(opportunities) if o["id"] not in settled]


def counts(opportunities: list[dict[str, Any]],
           pipeline: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The one place the detected/recommended/decided relationship is expressed.

    Pass the pipeline to get the decision split as well. Without it the counts
    describe what the engine chose; with it they also describe what the advisor
    has done about it.
    """
    detected = len(opportunities)
    today = sum(1 for o in opportunities if o.get("prioritized_today"))
    eligible = sum(1 for o in opportunities
                   if o["priority"] >= PRIORITY_BAR and o["contactable"])
    decision_split: dict[str, Any] = {}
    if pipeline is not None:
        waiting = len(awaiting_decision(opportunities, pipeline))
        decision_split = {
            # Still in the inbox.
            "awaiting_decision": waiting,
            # Ruled on. Together these always equal prioritized_today, which
            # never shrinks — deciding is progress through the day, not a
            # smaller day.
            "decisions_made": today - waiting,
        }
    return {
        "detected": detected,
        "prioritized_today": today,
        **decision_split,
        # Cleared the bar but sat outside the day's capacity. Naming this keeps
        # the cap honest: these were held back, not judged unworthy.
        "held_back": max(0, eligible - today),
        "not_contactable": sum(1 for o in opportunities if not o["contactable"]),
        "daily_cap": DAILY_CAP,
        "priority_bar": PRIORITY_BAR,
    }


# --------------------------------------------------------------- action log ---

# The advisor's workflow, in the order work actually moves through a boutique.
ACTION_STATES = ["Approved", "Scheduled", "Contacted", "Converted", "Ignored"]
OPEN_STATES = {"Approved", "Scheduled", "Contacted"}
CLOSED_STATES = {"Converted", "Ignored"}


def pipeline_defaults(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Seed an Action Center row per opportunity, awaiting the advisor."""
    rows: list[dict[str, Any]] = []
    for opp in opportunities:
        rows.append({
            "id": opp["id"],
            "customer_id": opp["customer_id"],
            "customer_name": opp["customer_name"],
            "value_tier": opp.get("value_tier"),
            "lifecycle": opp.get("lifecycle"),
            "trigger": opp["trigger"],
            "reason": opp["why_now"],
            "prioritized_today": bool(opp.get("prioritized_today")),
            "product": (opp.get("product") or {}).get("name"),
            "product_sku": (opp.get("product") or {}).get("sku"),
            "match_pct": (opp.get("product") or {}).get("match_pct"),
            "channel": (opp["eligibility"].get("preferred_channel") or {}).get("label"),
            "contactable": opp["contactable"],
            "influenced_value": opp.get("influenced_value"),
            "incremental_value": opp.get("incremental_value"),
            "priority": opp["priority"],
            "status": "New",
            "note": None,
            "created_at": datetime.utcnow().isoformat(timespec="seconds"),
            "updated_at": None,
        })
    rows.sort(key=lambda r: -r["priority"])
    return rows
