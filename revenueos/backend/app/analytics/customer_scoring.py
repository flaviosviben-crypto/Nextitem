"""Customer profiling: metrics, affinities and scores.

Everything here is deterministic. Transactions are the preferred source; when
they are absent we fall back to summary columns from the CRM export and mark the
profile's ``data_confidence`` accordingly. A metric that cannot be computed is
``None`` — the UI renders that as "Not enough information", never as 0.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from . import reference_date, taxonomy

# Affinity below this share of spend is noise, not a preference.
_MIN_AFFINITY_SHARE = 0.12


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or not b:
        return None
    return a / b


def _share_map(pairs: Iterable[tuple[str | None, float]]) -> dict[str, float]:
    """Turn (label, value) pairs into a normalised share-of-total map."""
    totals: dict[str, float] = defaultdict(float)
    for label, value in pairs:
        if label and value and value > 0:
            totals[str(label)] += float(value)
    grand = sum(totals.values())
    if grand <= 0:
        return {}
    return {k: v / grand for k, v in sorted(totals.items(), key=lambda kv: -kv[1])}


def _dominant(shares: dict[str, float]) -> tuple[str | None, float | None]:
    if not shares:
        return None, None
    label, share = next(iter(shares.items()))
    return (label, share) if share >= _MIN_AFFINITY_SHARE else (label, share)


# No fashion customer genuinely repurchases faster than this. Two visits in one
# week are one shopping occasion, not a two-day buying cycle — without a floor a
# customer like that reads as "215x overdue" and dominates every ranking.
_MIN_CADENCE_DAYS = 14.0
_MIN_CADENCE_SINGLE_GAP = 21.0


def _median_gap_days(dates: list[date]) -> tuple[float, int] | None:
    """Median spacing between distinct purchase days, plus how many gaps backed it.

    The gap count is what tells the segmentation layer whether this cadence is
    the customer's own rhythm or a coin flip that needs a cohort behind it.
    """
    uniq = sorted(set(dates))
    if len(uniq) < 2:
        return None
    gaps = [(b - a).days for a, b in zip(uniq, uniq[1:]) if 0 < (b - a).days < 1095]
    if not gaps:
        return None
    median = float(statistics.median(gaps))
    # One gap is an anecdote, not a cadence: hold it to a wider floor.
    floor = _MIN_CADENCE_DAYS if len(gaps) >= 2 else _MIN_CADENCE_SINGLE_GAP
    return max(floor, median), len(gaps)


def build_profiles(
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Compute one enriched profile per customer.

    Customers present only in the transaction file are included, so a boutique
    that exports sales without a CRM still gets a full customer base.
    """
    tx_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in transactions:
        tx_by_customer[t["customer_id"]].append(t)

    if as_of is None:
        as_of = reference_date.resolve_as_of(transactions, customers)

    base = {c["customer_id"]: c for c in customers}
    for cid in tx_by_customer:
        base.setdefault(cid, {"customer_id": cid, "name": cid, "_derived": True})

    profiles = [_profile_one(rec, tx_by_customer.get(rec["customer_id"], []), as_of)
                for rec in base.values()]

    _attach_relative_scores(profiles)
    return profiles


def _profile_one(rec: dict[str, Any], txs: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    cid = rec["customer_id"]
    dated = sorted([t for t in txs if t.get("date")], key=lambda t: t["date"])
    has_tx = bool(txs)

    # ---- money & counts ----
    if has_tx:
        total_spend = sum(t["line_total"] for t in txs)
        baskets: dict[str, float] = defaultdict(float)
        for t in txs:
            baskets[t["transaction_id"]] += t["line_total"]
        order_count = len(baskets)
        avg_order_value = total_spend / order_count if order_count else None
        spend_source = "transactions"
        units = sum(int(t.get("quantity") or 1) for t in txs)
    else:
        total_spend = rec.get("total_spend")
        order_count = int(rec["num_purchases"]) if rec.get("num_purchases") else None
        avg_order_value = rec.get("avg_order_value")
        if avg_order_value is None and total_spend is not None and order_count:
            avg_order_value = total_spend / order_count
        spend_source = "crm summary" if total_spend is not None else "unavailable"
        units = None

    # ---- dates ----
    first_purchase = dated[0]["date"] if dated else rec.get("first_purchase_date")
    last_purchase = dated[-1]["date"] if dated else rec.get("last_purchase_date")
    recency_days = (as_of - last_purchase).days if last_purchase else None
    tenure_days = (as_of - first_purchase).days if first_purchase else None

    observed = _median_gap_days([t["date"] for t in dated]) if dated else None
    cadence, gap_count = observed if observed else (None, 0)
    if cadence is None and tenure_days and order_count and order_count > 1:
        # Spread the tenure over the known orders. It is a real observation, but a
        # coarse one — count it as a single gap so it never poses as a rhythm.
        cadence = max(_MIN_CADENCE_DAYS, tenure_days / (order_count - 1))
        gap_count = 1

    overdue_ratio = _safe_div(recency_days, cadence) if cadence else None

    frequency_per_year = None
    if order_count and tenure_days and tenure_days >= 60:
        frequency_per_year = order_count / (tenure_days / 365.25)
    elif cadence:
        frequency_per_year = 365.25 / cadence

    # ---- affinities ----
    cat_shares = _share_map((t.get("category"), t["line_total"]) for t in txs)
    brand_shares = _share_map((t.get("brand"), t["line_total"]) for t in txs)
    color_shares = _share_map((t.get("color"), t["line_total"]) for t in txs)
    size_shares = _share_map((t.get("size"), float(t.get("quantity") or 1)) for t in txs)

    # Sizes are only comparable within a product family: a customer is an "M" in
    # knitwear and a "38" in shoes. Pooling them would make every size look right.
    size_by_family: dict[str, dict[str, float]] = {}
    grouped: dict[str, list[tuple[str | None, float]]] = defaultdict(list)
    for t in txs:
        family = taxonomy.family_of(t.get("category"))
        if family and t.get("size"):
            grouped[family].append((t.get("size"), float(t.get("quantity") or 1)))
    for family, pairs in grouped.items():
        shares = _share_map(pairs)
        if shares:
            size_by_family[family] = {k: round(v, 3) for k, v in list(shares.items())[:3]}

    if not cat_shares and rec.get("preferred_category"):
        cat_shares = {str(rec["preferred_category"]): 1.0}
    if not brand_shares and rec.get("preferred_brand"):
        brand_shares = {str(rec["preferred_brand"]): 1.0}
    if not color_shares and rec.get("color"):
        color_shares = {str(rec["color"]): 1.0}
    if not size_shares and rec.get("size"):
        size_shares = {str(rec["size"]): 1.0}

    # ---- price band ----
    unit_prices = [t["unit_price"] for t in txs
                   if t.get("unit_price") and t["unit_price"] > 0]
    if unit_prices:
        srt = sorted(unit_prices)
        price_median = statistics.median(srt)
        price_low = srt[max(0, int(len(srt) * 0.15) - 1)]
        price_high = srt[min(len(srt) - 1, int(len(srt) * 0.85))]
    elif avg_order_value:
        price_median = avg_order_value
        price_low, price_high = avg_order_value * 0.6, avg_order_value * 1.6
    else:
        price_median = price_low = price_high = None

    # ---- discount behaviour ----
    discounted = [t for t in txs if t.get("discount")]
    if txs:
        discount_share = len(discounted) / len(txs)
    else:
        discount_share = rec.get("discount_sensitivity")

    # ---- trajectory: last 12 months vs the 12 before ----
    spend_growth = None
    if dated and tenure_days and tenure_days > 400:
        cutoff = as_of - timedelta(days=365)
        prior_cutoff = as_of - timedelta(days=730)
        recent = sum(t["line_total"] for t in dated if t["date"] > cutoff)
        previous = sum(t["line_total"] for t in dated if prior_cutoff < t["date"] <= cutoff)
        if previous > 0:
            spend_growth = (recent - previous) / previous
        elif recent > 0:
            spend_growth = 1.0

    sku_history = {t["sku"] for t in txs if t.get("sku")}

    # ---- how much do we actually know? ----
    signals = sum([
        bool(has_tx), bool(dated), bool(cat_shares), bool(brand_shares),
        bool(unit_prices), bool(size_shares), total_spend is not None,
    ])
    data_confidence = "High" if signals >= 6 else "Medium" if signals >= 3 else "Low"

    top_cat, top_cat_share = _dominant(cat_shares)
    top_brand, top_brand_share = _dominant(brand_shares)

    return {
        "customer_id": cid,
        "name": rec.get("name") or cid,
        # True when this person exists only in the transaction file: the UI says so
        # rather than showing a bare ID and letting the advisor wonder.
        "crm_record": not rec.get("_derived", False),
        "email": rec.get("email"),
        "city": rec.get("city"),
        "country": rec.get("country"),
        "store": rec.get("store") or _mode([t.get("store") for t in txs]),
        # No CRM field for this — it only ever comes from who rang up the sale.
        "advisor": _mode([t.get("advisor") for t in txs]),
        "gender": rec.get("gender"),
        "phone": rec.get("phone"),
        "marketing_consent": rec.get("marketing_consent"),
        # Carried through untouched for the compliance layer to resolve. Consent
        # is not a metric, so nothing here interprets it.
        "email_consent": rec.get("email_consent"),
        "sms_consent": rec.get("sms_consent"),
        "whatsapp_consent": rec.get("whatsapp_consent"),
        "phone_consent": rec.get("phone_consent"),
        "do_not_contact": rec.get("do_not_contact"),
        "last_contacted_date": rec.get("last_contacted_date"),
        "source_segment": rec.get("segment"),

        "total_spend": round(total_spend, 2) if total_spend is not None else None,
        "spend_source": spend_source,
        "order_count": order_count,
        "units": units,
        "avg_order_value": round(avg_order_value, 2) if avg_order_value is not None else None,
        "first_purchase": first_purchase.isoformat() if first_purchase else None,
        "last_purchase": last_purchase.isoformat() if last_purchase else None,
        "recency_days": recency_days,
        "tenure_days": tenure_days,
        "cadence_days": round(cadence, 1) if cadence else None,
        "overdue_ratio": round(overdue_ratio, 2) if overdue_ratio else None,
        # What we actually saw, before segmentation decides whether it is enough
        # to stand on its own or needs a cohort to back it up.
        "observed_cycle_days": round(cadence, 1) if cadence else None,
        "cycle_gap_count": gap_count,
        "frequency_per_year": round(frequency_per_year, 2) if frequency_per_year else None,
        "spend_growth": round(spend_growth, 3) if spend_growth is not None else None,

        "category_affinity": {k: round(v, 3) for k, v in list(cat_shares.items())[:6]},
        "brand_affinity": {k: round(v, 3) for k, v in list(brand_shares.items())[:6]},
        "color_affinity": {k: round(v, 3) for k, v in list(color_shares.items())[:6]},
        "size_affinity": {k: round(v, 3) for k, v in list(size_shares.items())[:4]},
        "size_affinity_by_family": size_by_family,
        "top_category": top_cat,
        "top_category_share": round(top_cat_share, 3) if top_cat_share else None,
        "top_brand": top_brand,
        "top_brand_share": round(top_brand_share, 3) if top_brand_share else None,

        "price_median": round(price_median, 2) if price_median else None,
        "price_low": round(price_low, 2) if price_low else None,
        "price_high": round(price_high, 2) if price_high else None,
        "discount_share": round(discount_share, 3) if discount_share is not None else None,

        "purchased_skus": sorted(sku_history),
        "transaction_count": len(txs),
        "data_confidence": data_confidence,
        "as_of": as_of.isoformat(),
    }


def _mode(values: list[Any]) -> Any:
    vals = [v for v in values if v]
    if not vals:
        return None
    return max(set(vals), key=vals.count)


def _percentile_rank(sorted_vals: list[float], value: float) -> float:
    """Fraction of the population at or below ``value``."""
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


def _attach_relative_scores(profiles: list[dict[str, Any]]) -> None:
    """Score customers relative to this boutique's own population.

    Absolute thresholds are meaningless across boutiques (a €2k customer is a VIP
    in one store and average in another), so every score is a percentile within
    the uploaded dataset.
    """
    spends = sorted(p["total_spend"] for p in profiles if p.get("total_spend") is not None)
    freqs = sorted(p["frequency_per_year"] for p in profiles if p.get("frequency_per_year") is not None)
    aovs = sorted(p["avg_order_value"] for p in profiles if p.get("avg_order_value") is not None)

    for p in profiles:
        value_pct = _percentile_rank(spends, p["total_spend"]) if p.get("total_spend") is not None else None
        freq_pct = _percentile_rank(freqs, p["frequency_per_year"]) if p.get("frequency_per_year") is not None else None
        aov_pct = _percentile_rank(aovs, p["avg_order_value"]) if p.get("avg_order_value") is not None else None

        p["value_percentile"] = round(value_pct, 3) if value_pct is not None else None
        p["frequency_percentile"] = round(freq_pct, 3) if freq_pct is not None else None
        p["aov_percentile"] = round(aov_pct, 3) if aov_pct is not None else None

        # Engagement: how far through their normal cycle are they?
        overdue = p.get("overdue_ratio")
        if overdue is None:
            engagement = None
        elif overdue <= 1:
            engagement = 1.0 - 0.35 * overdue
        else:
            engagement = max(0.0, 0.65 - 0.35 * min(3.0, overdue - 1))
        p["engagement_score"] = round(engagement * 100) if engagement is not None else None

        # Customer score blends value, frequency and engagement over whatever exists.
        parts = [(value_pct, 0.45), (freq_pct, 0.25), (engagement, 0.30)]
        available = [(v, w) for v, w in parts if v is not None]
        if available:
            weight = sum(w for _, w in available)
            p["customer_score"] = round(sum(v * w for v, w in available) / weight * 100)
        else:
            p["customer_score"] = None

        # Potential value: what a comparable-but-fully-engaged customer spends.
        if p.get("avg_order_value") and p.get("frequency_per_year"):
            p["potential_annual_value"] = round(p["avg_order_value"] * p["frequency_per_year"], 2)
        elif p.get("total_spend") and p.get("tenure_days") and p["tenure_days"] > 90:
            p["potential_annual_value"] = round(p["total_spend"] / (p["tenure_days"] / 365.25), 2)
        else:
            p["potential_annual_value"] = None


def summarize_base(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Portfolio-level aggregates for the dashboard."""
    spends = [p["total_spend"] for p in profiles if p.get("total_spend") is not None]
    aovs = [p["avg_order_value"] for p in profiles if p.get("avg_order_value") is not None]
    cadences = [p["cadence_days"] for p in profiles if p.get("cadence_days")]
    overdue = [p for p in profiles if (p.get("overdue_ratio") or 0) > 1.25]
    contactable = [p for p in profiles if p.get("marketing_consent") is True]

    return {
        "customers": len(profiles),
        "total_spend": round(sum(spends), 2) if spends else None,
        "avg_spend": round(statistics.mean(spends), 2) if spends else None,
        "median_spend": round(statistics.median(spends), 2) if spends else None,
        "avg_order_value": round(statistics.mean(aovs), 2) if aovs else None,
        "median_cadence_days": round(statistics.median(cadences)) if cadences else None,
        "overdue_customers": len(overdue),
        "contactable": len(contactable),
        "consent_known": sum(1 for p in profiles if p.get("marketing_consent") is not None),
        "top_20_pct_share": _top_share(spends, 0.2),
    }


def _top_share(spends: list[float], fraction: float) -> float | None:
    if not spends:
        return None
    ordered = sorted(spends, reverse=True)
    cutoff = max(1, math.ceil(len(ordered) * fraction))
    total = sum(ordered)
    return round(sum(ordered[:cutoff]) / total, 3) if total else None
