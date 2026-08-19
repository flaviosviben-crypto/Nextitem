"""Customer metrics, RFM, inventory ageing and opportunity scoring."""
from __future__ import annotations

from datetime import date, timedelta

from app.analytics import (
    compliance, customer_scoring, inventory, opportunities, segmentation,
)

TODAY = date(2026, 8, 17)


def _tx(cid, days_ago, amount, category="Leather Goods", sku="A1", order=None, brand="Totême"):
    return {
        "customer_id": cid,
        "transaction_id": order or f"O-{cid}-{days_ago}",
        "date": TODAY - timedelta(days=days_ago),
        "line_total": amount, "unit_price": amount, "quantity": 1,
        "category": category, "brand": brand, "sku": sku, "color": "Black", "size": "M",
    }


def test_metrics_from_transactions():
    txs = [_tx("C1", 300, 500), _tx("C1", 200, 700), _tx("C1", 100, 900)]
    profiles = customer_scoring.build_profiles([{"customer_id": "C1", "name": "Anna"}], txs, TODAY)
    p = profiles[0]
    assert p["total_spend"] == 2100
    assert p["order_count"] == 3
    assert p["avg_order_value"] == 700
    assert p["recency_days"] == 100
    assert p["cadence_days"] == 100
    assert p["spend_source"] == "transactions"
    assert p["top_category"] == "Leather Goods"


def test_basket_lines_group_into_one_order():
    txs = [_tx("C1", 100, 300, order="O1"), _tx("C1", 100, 200, order="O1", sku="A2")]
    p = customer_scoring.build_profiles([{"customer_id": "C1", "name": "A"}], txs, TODAY)[0]
    assert p["order_count"] == 1
    assert p["avg_order_value"] == 500


def test_falls_back_to_crm_summary_without_transactions():
    customers = [{
        "customer_id": "C1", "name": "Anna", "total_spend": 3000,
        "num_purchases": 4, "last_purchase_date": TODAY - timedelta(days=40),
        "first_purchase_date": TODAY - timedelta(days=400),
    }]
    p = customer_scoring.build_profiles(customers, [], TODAY)[0]
    assert p["total_spend"] == 3000
    assert p["avg_order_value"] == 750
    assert p["spend_source"] == "crm summary"
    assert p["recency_days"] == 40


def test_unknown_metrics_are_none_never_zero():
    p = customer_scoring.build_profiles([{"customer_id": "C1", "name": "Anna"}], [], TODAY)[0]
    assert p["total_spend"] is None
    assert p["avg_order_value"] is None
    assert p["cadence_days"] is None
    assert p["data_confidence"] == "Low"


def test_customer_only_in_transactions_is_still_profiled():
    profiles = customer_scoring.build_profiles([], [_tx("GHOST", 30, 400)], TODAY)
    assert [p["customer_id"] for p in profiles] == ["GHOST"]


def _classified(customers, txs, today=TODAY):
    """Profiles through the real V1 pipeline: value, lifecycle, then eligibility."""
    profiles = customer_scoring.build_profiles(customers, txs, today)
    return compliance.apply(segmentation.classify(profiles), today)


def test_a_customer_just_past_their_cycle_is_due_not_lost():
    """The defect that made RevenueOS untrustworthy: 107% through a cycle is Due.

    A boutique customer a few days past their expected repurchase point is the
    single best person to call. Labelling them Lost both insults the relationship
    and buries the opportunity under a low-priority broadcast.
    """
    result = segmentation.classify_lifecycle(recency_days=107, cycle_days=100)
    assert result["lifecycle"] == "Due"
    assert result["cycle_position"] == 1.07


def test_lifecycle_boundaries_are_ordered_and_configurable():
    at = lambda days: segmentation.classify_lifecycle(days, 100)["lifecycle"]
    assert at(80) == "Active"      # inside their rhythm
    assert at(100) == "Active"     # exactly at the point is not yet late
    assert at(140) == "Due"        # just past it — the moment to make contact
    assert at(200) == "At Risk"    # meaningfully beyond
    assert at(400) == "Lost"       # genuinely lapsed

    # A jeweller and a denim store do not share a definition of overdue.
    patient = {"active_max": 2.0, "due_max": 3.0, "at_risk_max": 5.0}
    assert segmentation.classify_lifecycle(140, 100, patient)["lifecycle"] == "Active"


def test_value_and_lifecycle_are_independent():
    """A VIP can be Lost; a Standard customer can be Active. The pair carries it."""
    customers, txs = [], []
    for i in range(24):
        cid = f"C{i}"
        customers.append({"customer_id": cid, "name": f"Cust {i}", "marketing_consent": True})
        # Big spenders who lapsed, small spenders who are current.
        spend, offset = (4000, 700) if i % 2 else (200, 10)
        for n in range(4):
            txs.append(_tx(cid, offset + n * 40, spend, order=f"{cid}-{n}"))
    profiles = _classified(customers, txs)

    tiers = {p["value_tier"] for p in profiles}
    stages = {p["lifecycle"] for p in profiles}
    assert tiers & {"VIP", "Promising"}, "high spenders must reach an elevated tier"
    assert "Lost" in stages and "Active" in stages
    lapsed_high = [p for p in profiles if p["lifecycle"] == "Lost"
                   and p["value_tier"] in {"VIP", "Promising"}]
    assert lapsed_high, "value must survive a customer going quiet"
    for p in profiles:
        assert p["segment"] == f"{p['value_tier']} · {p['lifecycle']}"


def test_a_thin_history_never_states_a_confident_cycle():
    """Two receipts is not a rhythm. Say where the number came from, or say nothing."""
    customers = [{"customer_id": "THIN", "name": "Thin"}]
    txs = [_tx("THIN", 300, 400, order="a"), _tx("THIN", 200, 400, order="b")]
    p = _classified(customers, txs)[0]
    assert p["cycle_source"] != "customer"
    assert p["cycle_confidence"] in {"Medium", "Low", "None"}
    assert p["cycle_basis"], "an inferred cycle must say what it was inferred from"


def test_a_customer_with_no_history_gets_no_invented_cycle():
    p = _classified([{"customer_id": "NEW", "name": "New"}], [])[0]
    assert p["cycle_days"] is None
    assert p["cycle_source"] == "none"
    assert "Not enough purchase history" in p["cycle_basis"]


def test_unknown_consent_is_not_consent():
    profiles = compliance.apply([
        {"customer_id": "A", "email": "a@x.com", "marketing_consent": True},
        {"customer_id": "B", "email": "b@x.com", "marketing_consent": None},
        {"customer_id": "C", "email": "c@x.com", "do_not_contact": True},
    ], TODAY)
    by_id = {p["customer_id"]: p for p in profiles}
    assert by_id["A"]["contactable"] is True
    assert by_id["B"]["contactable"] is False
    assert by_id["C"]["contactable"] is False
    assert "not to be contacted" in by_id["C"]["suppression_reason"]


def test_a_channel_is_never_recommended_without_consent_and_a_way_to_reach_them():
    # Consent for WhatsApp but no phone number on file: the channel stays shut.
    elig = compliance.evaluate({"customer_id": "X", "whatsapp_consent": True,
                                "email_consent": True, "email": "x@x.com"}, TODAY)
    keys = {c["key"] for c in elig["channels"]}
    assert "whatsapp" not in keys
    assert "email" in keys

    # A specific refusal beats a general yes.
    elig = compliance.evaluate({"customer_id": "Y", "marketing_consent": True,
                                "email": "y@x.com", "email_consent": False}, TODAY)
    assert "email" not in {c["key"] for c in elig["channels"]}


def test_segments_adapt_to_the_dataset():
    """Tiers are percentiles within this boutique, not thresholds carried in."""
    customers, txs = [], []
    for i in range(30):
        cid = f"C{i}"
        customers.append({"customer_id": cid, "name": f"Cust {i}", "marketing_consent": True})
        # Spread of value and recency so the percentiles have something to bite on.
        for n in range(1 + i % 6):
            txs.append(_tx(cid, 30 + i * 12 + n * 45, 100 + i * 60, order=f"{cid}-{n}"))
    profiles = _classified(customers, txs)

    assert {p["value_tier"] for p in profiles} <= set(segmentation.VALUE_TIERS)
    assert {p["lifecycle"] for p in profiles} <= set(segmentation.LIFECYCLE_STAGES)
    assert len({p["segment"] for p in profiles}) >= 3, \
        "a varied dataset must produce a spread of value/lifecycle pairs"
    for p in profiles:
        assert p["value_basis"], "a tier the advisor cannot verify is not a tier"

    summary = segmentation.summarize(profiles)
    assert sum(row["customers"] for row in summary["value"]) == len(profiles)
    assert sum(row["customers"] for row in summary["lifecycle"]) == len(profiles)


def test_recency_is_relative_to_each_customers_cadence():
    """A twice-a-year buyer at 100 days is fine; a monthly buyer at 100 days is not."""
    customers = [{"customer_id": "SLOW", "name": "Slow"}, {"customer_id": "FAST", "name": "Fast"}]
    txs = [
        _tx("SLOW", 500, 900, order="s1"), _tx("SLOW", 320, 900, order="s2"),
        _tx("SLOW", 100, 900, order="s3"),
        _tx("FAST", 190, 900, order="f1"), _tx("FAST", 160, 900, order="f2"),
        _tx("FAST", 130, 900, order="f3"),
    ]
    profiles = customer_scoring.build_profiles(customers, txs, TODAY)
    by_id = {p["customer_id"]: p for p in profiles}
    assert by_id["SLOW"]["overdue_ratio"] < by_id["FAST"]["overdue_ratio"]


def test_inventory_ageing_and_risk():
    products = [
        {"sku": "OLD", "product_name": "Old Coat", "category": "Ready-to-Wear", "price": 800,
         "cost": 320, "stock": 6, "arrival_date": TODAY - timedelta(days=500)},
        {"sku": "NEW", "product_name": "New Coat", "category": "Ready-to-Wear", "price": 800,
         "cost": 320, "stock": 4, "arrival_date": TODAY - timedelta(days=20)},
    ]
    txs = [_tx("C1", 10, 800, sku="NEW"), _tx("C2", 5, 800, sku="NEW", order="O2")]
    stats = inventory.build_product_stats(products, txs, TODAY)
    by_sku = {p["sku"]: p for p in stats}

    assert by_sku["OLD"]["days_in_stock"] == 500
    assert by_sku["OLD"]["units_sold"] == 0
    assert by_sku["OLD"]["risk_score"] > by_sku["NEW"]["risk_score"]
    assert by_sku["OLD"]["risk_class"] in {"At Risk", "Dead Stock"}
    assert by_sku["OLD"]["risk_drivers"], "risk must be explainable"
    assert "discount" not in by_sku["OLD"]["recommended_action"].split(".")[0].lower()
    assert by_sku["OLD"]["stock_value"] == 4800
    assert by_sku["OLD"]["margin_rate"] == 0.6


def test_inventory_without_signals_is_unknown_not_risky():
    stats = inventory.build_product_stats(
        [{"sku": "X", "product_name": "Mystery", "category": "Shoes"}], [], TODAY)
    p = stats[0]
    assert p["risk_score"] is None
    assert p["risk_class"] == "Unknown"
    assert "Not enough information" in p["risk_reason"]


def test_sell_through_needs_both_halves():
    stats = inventory.build_product_stats(
        [{"sku": "X", "product_name": "P", "category": "Shoes", "price": 100}], [], TODAY)
    assert stats[0]["sell_through"] is None


def _opportunity_fixture():
    customers, txs = [], []
    for i in range(24):
        cid = f"C{i}"
        customers.append({"customer_id": cid, "name": f"Cust {i}",
                          "marketing_consent": True, "email": f"c{i}@boutique.test"})
        for n in range(4):
            txs.append(_tx(cid, 400 - n * 90 + i, 600 + i * 40, order=f"{cid}-{n}"))
    profiles = _classified(customers, txs)
    products = inventory.build_product_stats([
        {"sku": "A1", "product_name": "Tote", "category": "Leather Goods", "brand": "Totême",
         "price": 890, "cost": 340, "stock": 5, "arrival_date": TODAY - timedelta(days=400)},
        {"sku": "A2", "product_name": "New Tote", "category": "Leather Goods", "brand": "Totême",
         "price": 950, "cost": 360, "stock": 4, "arrival_date": TODAY - timedelta(days=15)},
    ], txs, TODAY)
    return profiles, products, txs


def test_every_opportunity_names_a_customer_a_reason_and_an_action():
    profiles, products, txs = _opportunity_fixture()
    found = opportunities.detect(profiles, products, txs, TODAY)
    assert found
    assert all(0 <= o["priority"] <= 100 for o in found)
    assert found == sorted(found, key=lambda o: -o["priority"])
    for o in found:
        assert o["customer_id"] and o["customer_name"]        # who
        assert o["why_now"]                                    # why now
        assert o["action"]                                     # how to act
        assert o["value_basis"], "every money figure must state its basis"
        assert "modelled" in o["probability_basis"].lower()


def test_one_customer_gets_one_opportunity():
    """Five cards for one person is a to-do list, not a recommendation."""
    profiles, products, txs = _opportunity_fixture()
    found = opportunities.detect(profiles, products, txs, TODAY)
    ids = [o["customer_id"] for o in found]
    assert len(ids) == len(set(ids))


def test_the_daily_list_is_never_padded_to_a_quota():
    """A quiet day is a short list, not a list of weak suggestions."""
    profiles, products, txs = _opportunity_fixture()
    found = opportunities.detect(profiles, products, txs, TODAY)
    shortlist = opportunities.daily(found, max_cards=20)
    assert len(shortlist) <= 20
    assert all(o["priority"] >= 55 for o in shortlist)
    # An empty engine yields an empty day, not filler.
    assert opportunities.daily([], max_cards=20) == []


def test_incremental_value_is_below_influenced_value():
    """We claim less than we observe, because some of it would have happened anyway."""
    profiles, products, txs = _opportunity_fixture()
    for o in opportunities.detect(profiles, products, txs, TODAY):
        if o.get("influenced_value"):
            assert o["incremental_value"] <= o["influenced_value"]


def test_lifecycle_alone_does_not_decide_priority():
    """A lapsed VIP must be able to outrank an active nobody."""
    vip = {"customer_id": "VIP", "name": "Vip", "value_tier": "VIP", "value_percentile": 0.97,
           "lifecycle": "Lost", "data_confidence": "High", "cycle_confidence": "High",
           "order_count": 8}
    small = {"customer_id": "SML", "name": "Small", "value_tier": "Standard",
             "value_percentile": 0.15, "lifecycle": "Due", "data_confidence": "Low",
             "cycle_confidence": "Low", "order_count": 1}
    trigger_lost = {"kind": "win_back", "headline": "", "why_now": ""}
    trigger_due = {"kind": "due", "headline": "", "why_now": ""}
    high = opportunities._priority(vip, trigger_lost, 0.09, 900, None, 1000, True)
    low = opportunities._priority(small, trigger_due, 0.30, 40, None, 1000, True)
    assert high > low


def test_a_customer_with_no_permitted_channel_is_ranked_below_a_reachable_one():
    profile = {"customer_id": "P", "name": "P", "value_tier": "VIP", "value_percentile": 0.9,
               "lifecycle": "Due", "data_confidence": "High", "cycle_confidence": "High",
               "order_count": 5}
    trigger = {"kind": "due", "headline": "", "why_now": ""}
    reachable = opportunities._priority(profile, trigger, 0.3, 500, None, 1000, True)
    blocked = opportunities._priority(profile, trigger, 0.3, 500, None, 1000, False)
    assert blocked < reachable


def test_portfolio_summary_handles_empty_dataset():
    summary = customer_scoring.summarize_base([])
    assert summary["customers"] == 0
    assert summary["total_spend"] is None


def test_cadence_has_a_believable_floor():
    """Two purchases a day apart must not read as a one-day buying cycle.

    Without a floor such a customer scores as hundreds of times overdue and
    dominates every ranking ahead of genuinely valuable clients.
    """
    txs = [_tx("C1", 216, 300, order="a"), _tx("C1", 215, 300, order="b")]
    p = customer_scoring.build_profiles([{"customer_id": "C1", "name": "Burst"}], txs, TODAY)[0]
    assert p["cadence_days"] >= 14
    assert p["overdue_ratio"] < 20, "a burst of visits must not produce an absurd overdue ratio"


def test_normal_cadence_is_not_distorted_by_the_floor():
    txs = [_tx("C1", 300, 500, order="a"), _tx("C1", 200, 500, order="b"),
           _tx("C1", 100, 500, order="c")]
    p = customer_scoring.build_profiles([{"customer_id": "C1", "name": "Steady"}], txs, TODAY)[0]
    assert p["cadence_days"] == 100
