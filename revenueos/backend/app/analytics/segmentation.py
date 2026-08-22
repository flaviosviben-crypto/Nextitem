"""Customer value and customer lifecycle — two separate dimensions.

The old model collapsed "how valuable is this customer" and "where are they in
their buying rhythm" into a single label, which produced commercially wrong
output: a VIP one day past their cycle was labelled the same as a lapsed
bargain-hunter, and "Lost" quietly demoted the customer to a low-priority
broadcast.

Here they are independent:

    Value      VIP  |  Promising  |  Standard        (how much they are worth)
    Lifecycle  Active | Due | At Risk | Lost         (where they are in the cycle)

A customer is "VIP · Due" or "Standard · Lost" — the pair carries the decision.
Neither dimension sets priority on its own; the opportunity engine combines them.

Buying cycles are only stated when the history supports them. With too few
purchases we fall back to a cohort median and say so, because a confident
"buys every 16 days" derived from two receipts is worse than an honest range.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

# ----------------------------------------------------------------- config ---

# Lifecycle boundaries, expressed as a multiple of the customer's expected
# buying cycle. Deliberately configurable: these are a sensible starting point
# for premium retail, not a universal truth.
LIFECYCLE_THRESHOLDS = {
    "active_max": 1.0,    # at or before the expected repurchase point
    "due_max": 1.5,       # just past it — the moment to make contact
    "at_risk_max": 2.5,   # meaningfully beyond their rhythm
    # anything above at_risk_max is Lost
}

# When no cycle can be estimated at all, fall back to absolute recency (days).
RECENCY_FALLBACK = {"active_max": 90, "due_max": 180, "at_risk_max": 365}

# A customer-level cycle needs this many observed gaps before we trust it.
MIN_GAPS_FOR_CUSTOMER_CYCLE = 3
MIN_GAPS_FOR_BLEND = 2

VALUE_TIERS = ["VIP", "Promising", "Standard"]
LIFECYCLE_STAGES = ["Active", "Due", "At Risk", "Lost"]

VALUE_META = {
    "VIP": {"tone": "positive", "rank": 3,
            "meaning": "Demonstrated high value — protect the relationship."},
    "Promising": {"tone": "positive", "rank": 2,
                  "meaning": "Rising trajectory — invest now to grow them into a VIP."},
    "Standard": {"tone": "neutral", "rank": 1,
                 "meaning": "No strong value signal yet."},
}

LIFECYCLE_META = {
    "Active": {"tone": "positive", "urgency": 0.25,
               "meaning": "Within their normal buying rhythm."},
    "Due": {"tone": "attention", "urgency": 1.0,
            "meaning": "At the point where another purchase would normally happen."},
    "At Risk": {"tone": "warning", "urgency": 0.85,
                "meaning": "Meaningfully beyond their normal rhythm."},
    "Lost": {"tone": "negative", "urgency": 0.55,
             "meaning": "Substantially beyond their rhythm — needs genuine win-back."},
}

# Used instead of LIFECYCLE_META's "meaning" whenever a customer (or the whole
# dataset) has no cycle to compare against at all — cycle_source "none", the
# RECENCY_FALLBACK branch of classify_lifecycle. That branch compares recency
# to fixed day windows, not to anything derived from a purchase pattern, so
# saying "rhythm" or "cycle" here would claim a personalisation the data does
# not support. A cohort-derived cycle (cycle_source "cohort"/"blended") still
# uses the buying-rhythm wording above: it is an estimate of a cycle, not an
# absence of one.
LIFECYCLE_META_RECENCY_FALLBACK = {
    "Active": "Purchased within the recent activity window.",
    "Due": "Beyond the first recency threshold.",
    "At Risk": "Well beyond the recent purchase window.",
    "Lost": "Inactive beyond the long-term recency threshold.",
}


# ------------------------------------------------------------ buying cycle ---

def _cohort_keys(profile: dict[str, Any]) -> list[tuple[str, str]]:
    """Cohorts to fall back through, most specific first."""
    keys: list[tuple[str, str]] = []
    category = profile.get("top_category")
    store = profile.get("store")
    if category and store:
        keys.append(("category_store", f"{category}|{store}"))
    if category:
        keys.append(("category", str(category)))
    if store:
        keys.append(("store", str(store)))
    return keys


def build_cohort_cycles(profiles: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Median observed cycle per cohort, from customers who have enough history.

    Only customers whose own cycle is trustworthy contribute, so the fallback a
    thin customer inherits is itself built from solid evidence.
    """
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    globals_: list[float] = []

    for p in profiles:
        observed = p.get("observed_cycle_days")
        gaps = p.get("cycle_gap_count") or 0
        if not observed or gaps < MIN_GAPS_FOR_CUSTOMER_CYCLE:
            continue
        globals_.append(observed)
        for kind, key in _cohort_keys(p):
            buckets[kind][key].append(observed)

    cohorts: dict[str, dict[str, float]] = {}
    for kind, keyed in buckets.items():
        cohorts[kind] = {
            key: float(statistics.median(values))
            for key, values in keyed.items()
            if len(values) >= 4          # a cohort needs a real population too
        }
    cohorts["global"] = {"all": float(statistics.median(globals_))} if globals_ else {}
    return cohorts


def resolve_cycle(profile: dict[str, Any], cohorts: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Decide this customer's expected buying cycle, and how much to trust it.

    Returns the cycle in days plus its provenance, so the UI can say
    "usually buys every 42 days" only when that is genuinely known.
    """
    observed = profile.get("observed_cycle_days")
    gaps = profile.get("cycle_gap_count") or 0

    def cohort_value() -> tuple[float | None, str | None]:
        for kind, key in _cohort_keys(profile):
            table = cohorts.get(kind, {})
            if key in table:
                label = {"category_store": "similar customers in this store",
                         "category": "customers buying the same category",
                         "store": "customers in this store"}[kind]
                return table[key], label
        world = cohorts.get("global", {}).get("all")
        return (world, "the customer base overall") if world else (None, None)

    if observed and gaps >= MIN_GAPS_FOR_CUSTOMER_CYCLE:
        return {
            "cycle_days": round(observed),
            "cycle_source": "customer",
            "cycle_confidence": "High",
            "cycle_basis": f"{gaps + 1} purchases on record",
        }

    cohort, cohort_label = cohort_value()

    if observed and gaps >= MIN_GAPS_FOR_BLEND:
        # Two gaps is a hint, not a pattern: pull it toward the cohort.
        blended = (observed + cohort) / 2 if cohort else observed
        return {
            "cycle_days": round(blended),
            "cycle_source": "blended",
            "cycle_confidence": "Medium",
            "cycle_basis": (f"{gaps + 1} purchases, adjusted toward {cohort_label}"
                            if cohort else f"{gaps + 1} purchases on record"),
        }

    if cohort:
        return {
            "cycle_days": round(cohort),
            "cycle_source": "cohort",
            "cycle_confidence": "Low",
            "cycle_basis": f"Typical for {cohort_label} — too few purchases to be sure",
        }

    return {
        "cycle_days": None,
        "cycle_source": "none",
        "cycle_confidence": "None",
        "cycle_basis": "Not enough purchase history to estimate a cycle",
    }


# -------------------------------------------------------------- lifecycle ---

def classify_lifecycle(recency_days: int | None, cycle_days: float | None,
                       thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """Where is this customer in their own buying rhythm?

    Passing the expected cycle means *Due* — the moment to make contact — not
    lost. Only a customer far beyond their rhythm is genuinely lapsed.
    """
    t = {**LIFECYCLE_THRESHOLDS, **(thresholds or {})}

    if recency_days is None:
        return {"lifecycle": "Active", "cycle_position": None,
                "lifecycle_basis": "No purchase date on record", "lifecycle_confidence": "None"}

    if not cycle_days:
        r = RECENCY_FALLBACK
        stage = ("Active" if recency_days <= r["active_max"]
                 else "Due" if recency_days <= r["due_max"]
                 else "At Risk" if recency_days <= r["at_risk_max"]
                 else "Lost")
        return {
            "lifecycle": stage,
            "cycle_position": None,
            "lifecycle_basis": f"{recency_days} days since last purchase (no cycle available)",
            "lifecycle_confidence": "Low",
        }

    position = recency_days / cycle_days
    stage = ("Active" if position <= t["active_max"]
             else "Due" if position <= t["due_max"]
             else "At Risk" if position <= t["at_risk_max"]
             else "Lost")
    return {
        "lifecycle": stage,
        "cycle_position": round(position, 2),
        "lifecycle_basis": (f"{recency_days} days since last purchase, against a "
                            f"{round(cycle_days)}-day cycle ({position:.0%} through it)"),
        "lifecycle_confidence": "High",
    }


# ------------------------------------------------------------------ value ---

def _percentile_table(values: list[float]) -> list[float]:
    return sorted(values)


def _percentile(sorted_vals: list[float], value: float) -> float:
    if not sorted_vals:
        return 0.0
    lo, hi = 0, len(sorted_vals)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_vals[mid] <= value:
            lo = mid + 1
        else:
            hi = mid
    return lo / len(sorted_vals)


def assign_value_tiers(profiles: list[dict[str, Any]]) -> None:
    """Score value against this boutique's own population, then tier it.

    Absolute thresholds do not travel between retailers, so everything is a
    percentile within the uploaded base. The composite stays in the backend;
    the visible output is one of three defensible labels.
    """
    spends = _percentile_table([p["total_spend"] for p in profiles
                                if p.get("total_spend") is not None])
    freqs = _percentile_table([p["frequency_per_year"] for p in profiles
                               if p.get("frequency_per_year") is not None])
    aovs = _percentile_table([p["avg_order_value"] for p in profiles
                              if p.get("avg_order_value") is not None])

    for p in profiles:
        spend_pct = (_percentile(spends, p["total_spend"])
                     if p.get("total_spend") is not None else None)
        freq_pct = (_percentile(freqs, p["frequency_per_year"])
                    if p.get("frequency_per_year") is not None else None)
        aov_pct = (_percentile(aovs, p["avg_order_value"])
                   if p.get("avg_order_value") is not None else None)

        parts = [(spend_pct, 0.5), (freq_pct, 0.25), (aov_pct, 0.25)]
        live = [(v, w) for v, w in parts if v is not None]
        composite = (sum(v * w for v, w in live) / sum(w for _, w in live)) if live else None

        # Momentum: are they on the way up? Spend growth, basket growth and a
        # widening category range all point at a customer worth investing in.
        growth = p.get("spend_growth")
        breadth = len(p.get("category_affinity") or {})
        full_price = 1 - (p.get("discount_share") or 0)
        orders = p.get("order_count") or 0

        momentum = 0.0
        signals: list[str] = []
        if growth is not None and growth >= 0.25:
            momentum += min(1.0, growth) * 0.5
            signals.append(f"Spend up {growth:.0%} year on year")
        if breadth >= 2:
            momentum += 0.2
            signals.append(f"Buying across {breadth} categories")
        if full_price >= 0.8 and orders >= 2:
            momentum += 0.2
            signals.append("Buys mostly at full price")
        if (freq_pct or 0) >= 0.6 and orders >= 3:
            momentum += 0.2
            signals.append("Purchasing more often than most customers")
        momentum = min(1.0, momentum)

        p["value_percentile"] = round(composite, 3) if composite is not None else None
        p["value_momentum"] = round(momentum, 3)
        p["value_signals"] = signals

        if composite is None:
            tier, why = "Standard", "Not enough spending history to classify"
        elif composite >= 0.85 or (spend_pct or 0) >= 0.95:
            tier = "VIP"
            why = (f"Top {(1 - (spend_pct or composite)):.0%} of the customer base by value"
                   if spend_pct is not None else "Among the highest-value customers")
        elif momentum >= 0.5 and composite >= 0.45 and orders >= 2:
            tier = "Promising"
            why = "; ".join(signals[:2]) or "Rising spending trajectory"
        elif composite >= 0.7:
            tier = "Promising"
            why = "Consistently above-average value"
        else:
            tier = "Standard"
            why = "No strong value signal yet"

        p["value_tier"] = tier
        p["value_basis"] = why
        p["value_tone"] = VALUE_META[tier]["tone"]
        p["value_rank"] = VALUE_META[tier]["rank"]


# ------------------------------------------------------------------ apply ---

def classify(profiles: list[dict[str, Any]],
             thresholds: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """Attach value tier, resolved cycle and lifecycle to every profile."""
    assign_value_tiers(profiles)
    cohorts = build_cohort_cycles(profiles)

    for p in profiles:
        cycle = resolve_cycle(p, cohorts)
        p.update(cycle)
        p.update(classify_lifecycle(p.get("recency_days"), cycle["cycle_days"], thresholds))

        # Keep the legacy fields consistent with the resolved cycle so nothing
        # downstream can quietly disagree with the badge shown to the advisor.
        p["cadence_days"] = cycle["cycle_days"]
        p["overdue_ratio"] = p.get("cycle_position")
        p["segment"] = f"{p['value_tier']} · {p['lifecycle']}"
        p["lifecycle_tone"] = LIFECYCLE_META[p["lifecycle"]]["tone"]
        # Recency-fallback wording when there is no cycle — of any provenance
        # — to compare against; buying-rhythm wording otherwise, including a
        # cohort-estimated cycle, which is still an estimate of a rhythm.
        p["lifecycle_meaning"] = (LIFECYCLE_META_RECENCY_FALLBACK[p["lifecycle"]]
                                  if cycle["cycle_source"] == "none"
                                  else LIFECYCLE_META[p["lifecycle"]]["meaning"])
    return profiles


def summarize(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts for the customer base, by value and by lifecycle."""
    by_value: dict[str, int] = defaultdict(int)
    by_lifecycle: dict[str, int] = defaultdict(int)
    matrix: dict[str, int] = defaultdict(int)
    value_amounts: dict[str, float] = defaultdict(float)

    for p in profiles:
        tier = p.get("value_tier", "Standard")
        stage = p.get("lifecycle", "Active")
        by_value[tier] += 1
        by_lifecycle[stage] += 1
        matrix[f"{tier}|{stage}"] += 1
        value_amounts[tier] += p.get("total_spend") or 0

    # A per-stage legend describes the whole workspace, not one customer, so it
    # cannot mix wording the way a per-profile ``lifecycle_meaning`` can. If
    # every customer here is on the recency fallback — no transaction history
    # at all to estimate any cycle from, personal or cohort — the legend says
    # so rather than describing a "buying rhythm" the dataset cannot show.
    recency_fallback_only = bool(profiles) and all(
        p.get("cycle_source") in (None, "none") for p in profiles)
    lifecycle_meaning = (LIFECYCLE_META_RECENCY_FALLBACK if recency_fallback_only
                         else {s: LIFECYCLE_META[s]["meaning"] for s in LIFECYCLE_STAGES})

    return {
        "value": [{"tier": t, "customers": by_value.get(t, 0),
                   "total_spend": round(value_amounts.get(t, 0), 2),
                   "meaning": VALUE_META[t]["meaning"]}
                  for t in VALUE_TIERS if by_value.get(t)],
        "lifecycle": [{"stage": s, "customers": by_lifecycle.get(s, 0),
                       "meaning": lifecycle_meaning[s]}
                      for s in LIFECYCLE_STAGES if by_lifecycle.get(s)],
        "matrix": [{"value_tier": t, "lifecycle": s, "customers": matrix[f"{t}|{s}"]}
                   for t in VALUE_TIERS for s in LIFECYCLE_STAGES if matrix.get(f"{t}|{s}")],
    }
