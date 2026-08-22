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

from . import compliance, matching, reference_date

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

# How many customers in one detection pass may be pointed at the same SKU as
# their top pick. Without a cap, one strong catalogue match can legitimately
# top dozens of cards in a row — technically correct, but it reads as a
# simplistic engine. Once a SKU hits the cap, later customers see their next
# genuine best match instead — never a product below MIN_MATCH_SCORE just for
# variety's sake.
SKU_EXPOSURE_CAP = 3

_CONFIDENCE_VALUE = {"High": 1.0, "Medium": 0.8, "Low": 0.55, "None": 0.4}


def _plural_days(value: int | None) -> str:
    if value is None:
        return "recently"
    return "1 day" if value == 1 else f"{value} days"


# ----------------------------------------------------------------- triggers ---

def _cycle_why_now(stage: str, profile: dict[str, Any], recency: int | None,
                   cycle: float | None, position: float | None, confidence: str) -> str:
    """State the timing as a fact the advisor can repeat, not a rule they infer.

    A raw recency-and-cycle-length pair makes the reader do the subtraction
    themselves. Leading with the overdue amount says the same thing faster —
    and a fallback cycle says plainly that it is a fallback, rather than
    dressing a cohort estimate up as this customer's own rhythm.
    """
    if not cycle or not position:
        # No personal cycle to fall back on. Say plainly what the timing rests
        # on instead of a bare recency figure that reads as more confident
        # than it is — a boutique with no transaction history at all is not
        # in the same position as one with two purchases on record.
        if profile.get("spend_source") == "transactions":
            return (f"Last bought {_plural_days(recency)} ago — not enough purchase "
                    "history yet for a personalized cycle.")
        return f"Based on CRM recency summary · last purchase {_plural_days(recency)} ago."

    if confidence == "Low":
        tier = (profile.get("value_tier") or "similar").lower()
        return f"Beyond the expected cycle for similar {tier} customers — limited personal history."

    qualifier = "" if confidence == "High" else " (estimated cycle)"

    if stage == "Due":
        overdue = round(recency - cycle) if recency is not None else None
        if overdue and overdue > 0:
            return f"{_plural_days(overdue)} beyond their usual {round(cycle)}-day cycle{qualifier}."
        return f"Last bought {_plural_days(recency)} ago, against a {round(cycle)}-day cycle{qualifier}."

    # At Risk / Lost are further past the cycle, where a percentage over
    # communicates the severity better than a raw day count does.
    pct_over = round((position - 1) * 100)
    if pct_over > 0:
        return f"Purchase gap is {pct_over}% longer than usual{qualifier}."
    return f"Last bought {_plural_days(recency)} ago, against a {round(cycle)}-day cycle{qualifier}."


def _lifecycle_trigger(profile: dict[str, Any]) -> dict[str, Any] | None:
    """The customer's own buying rhythm says it is time."""
    stage = profile.get("lifecycle")
    if stage not in {"Due", "At Risk", "Lost"}:
        return None

    recency = profile.get("recency_days")
    position = profile.get("cycle_position")
    cycle = profile.get("cycle_days")
    confidence = profile.get("cycle_confidence") or "Low"

    # No cycle of any provenance — personal or cohort — to compare against:
    # a pure recency fallback, which "usual rhythm" would misrepresent as a
    # personalised cadence. This headline is the first thing Customer Detail
    # shows, so it carries the same distinction as the lifecycle legend.
    has_cycle = profile.get("cycle_source") not in (None, "none")

    if stage == "Due":
        kind, headline = "due", "Due for their next purchase"
    elif stage == "At Risk":
        kind, headline = "at_risk", ("Drifting past their usual rhythm" if has_cycle
                                     else "Well beyond the recent purchase window")
    else:
        kind, headline = "win_back", "Lapsed — worth a genuine win-back"

    why = _cycle_why_now(stage, profile, recency, cycle, position, confidence)

    return {"kind": kind, "headline": headline, "why_now": why,
            "evidence": profile.get("lifecycle_basis")}


def _customer_evidence(profile: dict[str, Any]) -> list[str]:
    """3-5 concrete facts behind today's card — never one this profile's data
    does not actually support.

    "Why this customer" used to show one recency sentence and stop, which
    explains what RevenueOS saw but not why it matters. This states the
    cadence, the overdue amount, the relationship's scale, and — only when a
    real purchase history backs it — the behaviour that history shows.
    """
    has_tx = profile.get("spend_source") == "transactions"
    lines: list[str] = []

    cycle_days = profile.get("cycle_days")
    cycle_source = profile.get("cycle_source")
    recency = profile.get("recency_days")
    if cycle_days and cycle_source in ("customer", "blended"):
        lines.append(f"Usually buys every {round(cycle_days)} days")
        if recency is not None and recency > cycle_days:
            lines.append(f"Now {round(recency - cycle_days)} days beyond their normal cycle")
    elif cycle_days and cycle_source == "cohort":
        tier = (profile.get("value_tier") or "similar").lower()
        lines.append(f"Limited personal history — timing based on similar {tier} customers")
    elif recency is not None:
        if has_tx:
            lines.append(f"Last purchase {_plural_days(recency)} ago — too little "
                         "history yet for a personalized cycle")
        else:
            lines.append(f"Based on CRM recency summary — last purchase "
                         f"{_plural_days(recency)} ago")

    if profile.get("total_spend") is not None:
        lines.append(f"Lifetime spend €{profile['total_spend']:,.0f}")

    if profile.get("order_count"):
        n = profile["order_count"]
        lines.append(f"{n} previous {'order' if n == 1 else 'orders'}")

    # Taste claims need a real purchase record behind them — a single CRM
    # "preferred category" field is a guess, not an established affinity.
    if has_tx:
        if profile.get("avg_order_value"):
            lines.append(f"Average order value €{profile['avg_order_value']:,.0f}")
        share = profile.get("top_category_share") or 0
        if profile.get("top_category") and share >= 0.4:
            lines.append(f"Strong {profile['top_category'].lower()} affinity")

    if profile.get("value_tier"):
        lines.append(f"{profile['value_tier']} customer")

    return lines[:5]


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


def _basket_source(profile: dict[str, Any], match: dict[str, Any] | None,
                   basket: float | None) -> tuple[str | None, str | None]:
    """Where the number in ``_basket`` actually came from, in the advisor's words.

    Must stay mechanically tied to ``_basket`` — this is not a separate guess
    at an explanation, it names the exact inputs that function used. When both
    inputs are used, that is a blend, not "this customer's own basket": saying
    otherwise is the invented explanation the advisor cannot verify.
    """
    if basket is None:
        return None, None
    price = (match or {}).get("price")
    aov = profile.get("avg_order_value")
    from_transactions = profile.get("spend_source") == "transactions"
    order_count = profile.get("order_count") or 0

    if price and aov:
        history = (f"this customer's own average order value from {order_count} recorded "
                   f"order{'s' if order_count != 1 else ''}" if from_transactions
                   else "the customer's average order value from the CRM summary")
        return ("blended",
               f"Average of {history} (€{aov:,.0f}) and the recommended piece's "
               f"price (€{price:,.0f}).")
    if aov:
        return (("customer_history" if from_transactions else "crm_summary"),
               (f"Based on this customer's own average order value from purchase history."
                if from_transactions else
                "Based on the customer's average order value from the CRM summary."))
    if price:
        return ("product_price",
               "Based on the recommended piece's price — no purchase history is "
               "available for this customer yet.")
    return None, None


def _value_confidence(profile: dict[str, Any]) -> str:
    """How much to trust the expected-value number, in one honest word.

    Not the same scale as ``data_confidence`` (which grades a product-match
    signal), and not fabricated as a percentage — a categorical label is all
    the inputs justify. Reuses two facts already computed for the estimate
    itself: whether the basket/probability came from real purchase history
    (``spend_source``), and, when it did, whether that history is thin enough
    that ``_probability`` already discounts it for the same reason.
    """
    if profile.get("spend_source") != "transactions":
        return "Limited"
    if (profile.get("order_count") or 0) < 4:
        return "Medium"
    return "High"


_VALUE_CONFIDENCE_BASIS = {
    "High": "Based on this customer's own purchase history and order value.",
    "Medium": "Based on transaction history, but only a few orders on record.",
    "Limited": "Based on customer summary data — transaction history is not currently available.",
}


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
    product_matching_available: bool = True,
) -> list[dict[str, Any]]:
    """One opportunity per customer who genuinely warrants a conversation today.

    ``limit`` caps the list for display; it never pads it. A quiet day produces a
    short list, which is the honest answer.

    ``product_matching_available`` is the dataset-level fact the Data page's
    "Product matching" capability reports. When it is False, no opportunity
    gets a product attached — triggers that require one (new arrival,
    cross-sell, restock) simply do not fire, and only lifecycle-driven
    opportunities ("this customer is worth contacting today") remain. Showing
    a precise match percentage the boutique's own data cannot support would
    cost more trust than a plainer card.
    """
    if as_of is None:
        as_of = reference_date.resolve_as_of(transactions)

    product_index = {str(p["sku"]): p for p in products}

    baskets = [p["avg_order_value"] for p in profiles if p.get("avg_order_value")]
    value_scale = (statistics.median(baskets) if baskets else 500.0) or 500.0

    # Highest-value customers get first claim on a popular SKU; the exposure
    # cap then pushes everyone after them toward their own next-best match.
    ranked_profiles = sorted(profiles, key=lambda p: -(p.get("value_percentile") or 0))
    sku_exposure: dict[str, int] = {}

    found: list[dict[str, Any]] = []
    for profile in ranked_profiles:
        opp = _for_customer(profile, products, product_index, value_scale, as_of, sku_exposure,
                            product_matching_available)
        if opp:
            found.append(opp)

    found.sort(key=lambda o: -o["priority"])
    return found[:limit] if limit else found


def _for_customer(profile: dict[str, Any], products: list[dict[str, Any]],
                  product_index: dict[str, dict], value_scale: float,
                  as_of: date, sku_exposure: dict[str, int] | None = None,
                  product_matching_available: bool = True
                  ) -> dict[str, Any] | None:
    matches = (matching.best_products_for_customer(
        profile, products, limit=3, min_score=MIN_MATCH_SCORE)
        if products and product_matching_available else [])

    # Prefer this customer's best match that hasn't already been another
    # customer's top pick too many times today. If every candidate is already
    # at the cap, fall back to the genuine best rather than showing nothing —
    # a repeated recommendation is still an honest one.
    best = None
    if sku_exposure is not None:
        for m in matches:
            if sku_exposure.get(m["sku"], 0) < SKU_EXPOSURE_CAP:
                best = m
                break
    if best is None and matches:
        best = matches[0]
    if best is not None and sku_exposure is not None:
        sku_exposure[best["sku"]] = sku_exposure.get(best["sku"], 0) + 1

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

    basket_source, basket_source_label = _basket_source(profile, best, basket)

    return {
        "id": f"opp::{profile['customer_id']}::{trigger['kind']}",
        "customer_id": profile["customer_id"],
        "customer_name": profile.get("name"),
        "value_tier": profile.get("value_tier"),
        "lifecycle": profile.get("lifecycle"),
        "segment": profile.get("segment"),
        # Real relationships already in the data model — a CRM/transaction
        # store and the transactions' own advisor mode — never assigned here.
        "store": profile.get("store"),
        "advisor": profile.get("advisor"),

        "trigger": trigger["kind"],
        "headline": trigger["headline"],
        "why_now": trigger["why_now"],
        "evidence": trigger.get("evidence"),
        "customer_evidence": _customer_evidence(profile),

        "product": _product_card(best, product_index) if best else None,
        "alternatives": [_product_card(m, product_index) for m in matches if m is not best][:2],

        "action": _action_text(trigger, eligibility, best),
        "eligibility": eligibility,
        "contactable": eligible,

        # Money, stated twice and labelled: what a conversation is worth, and how
        # much of it we are prepared to claim as caused by RevenueOS.
        "basket_value": basket,
        "influenced_value": influenced,
        "incremental_value": incremental,
        # What basket_value actually is — traced from the same inputs
        # ``_basket`` used, never a separate guess at an explanation.
        "value_basis": basket_source_label or "Not enough spending history to estimate",
        "basket_source": basket_source,
        "probability": probability,
        "probability_basis": "Modelled from retail response benchmarks, not measured here",
        # Categorical, not a fabricated second percentage: how much to trust
        # the basket/probability inputs above, not the model math itself.
        "value_confidence": _value_confidence(profile) if basket else None,
        "value_confidence_basis": (_VALUE_CONFIDENCE_BASIS[_value_confidence(profile)]
                                   if basket else None),

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
           pipeline: list[dict[str, Any]] | None = None,
           daily_cap: int = DAILY_CAP,
           product_matching_available: bool = True) -> dict[str, Any]:
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
        "daily_cap": daily_cap,
        "priority_bar": PRIORITY_BAR,
        # The one fact that distinguishes "no product cleared the threshold"
        # from "product matching cannot be computed at all" — read by every
        # screen so a capability gap never looks like an ordinary no-match.
        "product_matching_available": product_matching_available,
    }


# --------------------------------------------------------------- action log ---

# The advisor's workflow, in the order work actually moves through a boutique.
ACTION_STATES = ["Approved", "Scheduled", "Contacted", "Converted", "Ignored"]

# Why an advisor set a recommendation aside. Stored as a code rather than the
# label, so the wording on screen can change without rewriting history and so
# the counts can be aggregated later — a boutique's own record of where the
# engine is wrong is worth more than any benchmark. Nothing reads these to
# score or rank anything yet; this is collection, not learning.
DECLINE_REASONS: dict[str, str] = {
    "wrong_product": "Wrong product",
    "contacted_recently": "Contacted recently",
    "low_relevance": "Low relevance",
    "save_for_later": "Save for later",
    "other": "Other",
}
OPEN_STATES = {"Approved", "Scheduled", "Contacted"}
CLOSED_STATES = {"Converted", "Ignored"}


def pipeline_defaults(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Seed an Action Center row per opportunity, awaiting the advisor.

    ``_generated`` fields snapshot the value/match/segment RevenueOS was
    looking at the moment this opportunity was first surfaced. They are only
    ever set here; ``_merge_pipeline`` freezes them on every later recompute
    so historical reporting reflects what was true when the recommendation was
    made, not whatever the engine currently thinks.
    """
    rows: list[dict[str, Any]] = []
    for opp in opportunities:
        match_pct = (opp.get("product") or {}).get("match_pct")
        prioritized = bool(opp.get("prioritized_today"))
        now = datetime.utcnow().isoformat(timespec="seconds")
        rows.append({
            "id": opp["id"],
            "customer_id": opp["customer_id"],
            "customer_name": opp["customer_name"],
            "value_tier": opp.get("value_tier"),
            "lifecycle": opp.get("lifecycle"),
            "store": opp.get("store"),
            "advisor": opp.get("advisor"),
            "trigger": opp["trigger"],
            "reason": opp["why_now"],
            "prioritized_today": prioritized,
            "product": (opp.get("product") or {}).get("name"),
            "product_sku": (opp.get("product") or {}).get("sku"),
            "match_pct": match_pct,
            "channel": (opp["eligibility"].get("preferred_channel") or {}).get("label"),
            "contactable": opp["contactable"],
            "influenced_value": opp.get("influenced_value"),
            "incremental_value": opp.get("incremental_value"),
            "priority": opp["priority"],
            "status": "New",
            "note": None,
            "created_at": now,
            "updated_at": None,
            "segment_generated": opp.get("segment"),
            "match_pct_generated": match_pct,
            "influenced_value_generated": opp.get("influenced_value"),
            "incremental_value_generated": opp.get("incremental_value"),
            # Set immediately if this opportunity is prioritized the moment it
            # is first seen — otherwise left for _merge_pipeline to stamp the
            # first time a later recompute finds it prioritized.
            "first_prioritized_at": now if prioritized else None,
        })
    rows.sort(key=lambda r: -r["priority"])
    return rows
