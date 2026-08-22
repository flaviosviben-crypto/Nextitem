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


def test_lifecycle_wording_matches_the_data_that_backs_it():
    """The bug this defends against: a zero-transaction dataset compares
    recency to fixed day windows (segmentation.RECENCY_FALLBACK), yet the
    lifecycle badge used to say "within their normal buying rhythm" — a claim
    about a personal cadence the data cannot show at all.

    A resolved cycle — this customer's own, or a cohort estimate from peers —
    keeps the buying-rhythm wording; a pure recency fallback does not.
    """
    # Degraded dataset: CRM summary only, no transactions anywhere, so no
    # customer or cohort cycle can be estimated for anyone.
    customers = [
        {"customer_id": "A", "name": "Active", "last_purchase_date": TODAY - timedelta(days=10)},
        {"customer_id": "B", "name": "Due", "last_purchase_date": TODAY - timedelta(days=140)},
        {"customer_id": "C", "name": "Risky", "last_purchase_date": TODAY - timedelta(days=300)},
    ]
    profiles = segmentation.classify(customer_scoring.build_profiles(customers, [], TODAY))
    by_id = {p["customer_id"]: p for p in profiles}
    assert by_id["A"]["cycle_source"] == "none"
    for cid, stage in (("A", "Active"), ("B", "Due"), ("C", "At Risk")):
        assert by_id[cid]["lifecycle"] == stage
        meaning = by_id[cid]["lifecycle_meaning"]
        assert meaning == segmentation.LIFECYCLE_META_RECENCY_FALLBACK[stage]
        for claim in ("rhythm", "normally happen"):
            assert claim not in meaning.lower()

    summary = segmentation.summarize(profiles)
    by_stage = {row["stage"]: row["meaning"] for row in summary["lifecycle"]}
    assert by_stage["Active"] == segmentation.LIFECYCLE_META_RECENCY_FALLBACK["Active"]
    assert by_stage["Due"] == segmentation.LIFECYCLE_META_RECENCY_FALLBACK["Due"]


def test_lifecycle_wording_stays_personalised_when_a_cycle_is_known():
    """A full dataset with real purchase history gets the buying-rhythm wording
    — the fallback strings above must not leak into a dataset that can support
    a genuine cycle."""
    customers, txs = [], []
    for i in range(6):
        cid = f"C{i}"
        customers.append({"customer_id": cid, "name": f"Cust {i}"})
        for n in range(4):
            txs.append(_tx(cid, 40 + n * 45, 400, order=f"{cid}-{n}"))
    profiles = segmentation.classify(customer_scoring.build_profiles(customers, txs, TODAY))

    assert all(p["cycle_source"] == "customer" for p in profiles)
    for p in profiles:
        assert p["lifecycle_meaning"] == segmentation.LIFECYCLE_META[p["lifecycle"]]["meaning"]

    summary = segmentation.summarize(profiles)
    by_stage = {row["stage"]: row["meaning"] for row in summary["lifecycle"]}
    for stage, meaning in by_stage.items():
        assert meaning == segmentation.LIFECYCLE_META[stage]["meaning"]


def test_the_at_risk_trigger_headline_matches_the_data_mode_too():
    """Customer Detail renders the opportunity headline as its main heading —
    "Drifting past their usual rhythm" is the same overclaim as the lifecycle
    legend's old wording, and must follow the same rule."""
    recency_only = {"customer_id": "R", "name": "R", "lifecycle": "At Risk",
                    "cycle_source": "none", "recency_days": 200}
    trigger = opportunities._lifecycle_trigger(recency_only)
    assert trigger["headline"] == "Well beyond the recent purchase window"

    with_cycle = {"customer_id": "K", "name": "K", "lifecycle": "At Risk",
                 "cycle_source": "customer", "recency_days": 60, "cycle_days": 30,
                 "cycle_position": 2.0, "cycle_confidence": "High"}
    trigger = opportunities._lifecycle_trigger(with_cycle)
    assert trigger["headline"] == "Drifting past their usual rhythm"


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


def test_expected_value_reconciles_with_the_displayed_probability():
    """The bug this defends against: a UI showing '€986 x 35% = €340' when the
    real math is €986 x 34.5% = €340.

    basket_value and probability are exact internal figures; influenced_value
    must be exactly their product, and the UI displays probability to one
    decimal place (lossless, since probability is stored to three decimals —
    a tenth of a percentage point). Reconstructing from that displayed
    probability, rounded to whole-currency the way the UI renders money, must
    land within a euro of the displayed influenced_value.
    """
    profiles, products, txs = _opportunity_fixture()
    found = opportunities.detect(profiles, products, txs, TODAY)
    checked = 0
    for o in found:
        if o["basket_value"] is None:
            continue
        checked += 1
        assert round(o["basket_value"] * o["probability"], 2) == o["influenced_value"]

        displayed_probability = round(o["probability"], 3)  # what pct(value, 1) shows, exactly
        reconstructed = o["basket_value"] * displayed_probability
        assert abs(round(reconstructed) - round(o["influenced_value"])) <= 1
    assert checked, "fixture must produce at least one opportunity with a basket value"


def test_basket_value_source_is_traceable_and_honest():
    """Every basket figure must say which real inputs it came from — never a
    generic 'this customer's own basket' when the number is actually a blend
    with the recommended piece's price, or drawn from CRM summary data."""
    match = {"price": 950.0, "sku": "A2"}

    # Both a product price and a customer AOV: an honest description says it
    # is a blend of the two, and states both numbers.
    blended = {"spend_source": "transactions", "avg_order_value": 700.0, "order_count": 5}
    source, label = opportunities._basket_source(blended, match, 825.0)
    assert source == "blended"
    assert "700" in label and "950" in label
    assert "this customer's own" in label

    # AOV only, from real transactions: no product price to blend with.
    tx_only = {"spend_source": "transactions", "avg_order_value": 700.0, "order_count": 5}
    source, label = opportunities._basket_source(tx_only, None, 700.0)
    assert source == "customer_history"
    assert "purchase history" in label

    # AOV only, but from a CRM summary column, not measured transactions —
    # the boutique's own words, not RevenueOS's.
    crm_only = {"spend_source": "crm summary", "avg_order_value": 500.0, "order_count": 3}
    source, label = opportunities._basket_source(crm_only, None, 500.0)
    assert source == "crm_summary"
    assert "CRM" in label

    # No customer history at all: only the candidate product's price is real.
    no_history = {"spend_source": "unavailable", "avg_order_value": None, "order_count": 0}
    source, label = opportunities._basket_source(no_history, match, 950.0)
    assert source == "product_price"
    assert "no purchase history" in label.lower()

    # No basket at all: nothing to explain.
    assert opportunities._basket_source(no_history, None, None) == (None, None)


def test_generated_opportunities_never_claim_an_unsupported_basket_source():
    """A CRM-summary-only customer's card must not say 'own average basket'
    when the figure is drawn from CRM data, not measured purchase history."""
    # 200 days since their last purchase, no cycle to compare against (no
    # transaction history anywhere in the dataset): recency fallback lands
    # this customer past due_max (180) — worth a genuine "At Risk" card.
    customers = [{"customer_id": "C1", "name": "Anna", "total_spend": 3000,
                 "num_purchases": 4, "avg_order_value": 750,
                 "last_purchase_date": TODAY - timedelta(days=200),
                 "marketing_consent": True, "email": "a@x.com"}]
    profiles = _classified(customers, [])
    products = inventory.build_product_stats([], [], TODAY)
    found = opportunities.detect(profiles, products, [], TODAY)
    assert found, "fixture must actually produce a CRM-summary opportunity to check"
    for o in found:
        if o["basket_value"] is not None:
            assert o["basket_source"] in {"customer_history", "crm_summary",
                                          "product_price", "blended"}
            assert "own average basket" not in o["value_basis"]


def test_one_customer_gets_one_opportunity():
    """Five cards for one person is a to-do list, not a recommendation."""
    profiles, products, txs = _opportunity_fixture()
    found = opportunities.detect(profiles, products, txs, TODAY)
    ids = [o["customer_id"] for o in found]
    assert len(ids) == len(set(ids))


def test_todays_list_is_never_padded_to_a_quota():
    """A quiet day is a short list, not a list of weak suggestions."""
    profiles, products, txs = _opportunity_fixture()
    found = opportunities.detect(profiles, products, txs, TODAY)
    shortlist = opportunities.prioritize(found, max_cards=20)
    assert len(shortlist) <= 20
    assert all(o["priority"] >= opportunities.PRIORITY_BAR for o in shortlist)
    assert all(o["contactable"] for o in shortlist)
    # An empty engine yields an empty day, not filler.
    assert opportunities.prioritize([], max_cards=20) == []


def test_detected_and_prioritized_are_different_numbers_with_one_definition():
    """The product's central claim: a large universe, a small daily workload.

    Detection and prioritisation must be separable and reconcilable, because
    every screen quotes these two numbers and they have to agree.
    """
    profiles, products, txs = _opportunity_fixture()
    detected = opportunities.detect(profiles, products, txs, TODAY)
    today = opportunities.prioritize(detected, max_cards=5)
    counts = opportunities.counts(detected)

    assert counts["detected"] == len(detected)
    assert counts["prioritized_today"] == len(today)
    assert len(today) <= len(detected), "today's list is drawn from what was detected"

    # The stamp is the single source of truth, and it partitions the universe.
    stamped = [o for o in detected if o["prioritized_today"]]
    assert stamped == today
    assert opportunities.todays_list(detected) == today
    assert all(o["prioritized_today"] is False
               for o in detected if o not in today)


def test_prioritisation_is_a_rule_not_a_display_limit():
    """Both the bar and the cap are real, and the difference is named."""
    profiles, products, txs = _opportunity_fixture()
    detected = opportunities.detect(profiles, products, txs, TODAY)
    opportunities.prioritize(detected, max_cards=3, bar=opportunities.PRIORITY_BAR)
    counts = opportunities.counts(detected)

    # Anything below the bar is excluded on merit; anything above it that did not
    # fit is held back, and the two reasons are reported separately so a short
    # list never gets confused with a filtered one.
    assert counts["prioritized_today"] <= 3
    eligible = [o for o in detected
                if o["priority"] >= opportunities.PRIORITY_BAR and o["contactable"]]
    assert counts["held_back"] == len(eligible) - counts["prioritized_today"]
    assert counts["not_contactable"] == sum(1 for o in detected if not o["contactable"])


def test_re_prioritising_never_leaves_a_stale_stamp():
    """Yesterday's selection must not linger and inflate today's count."""
    profiles, products, txs = _opportunity_fixture()
    detected = opportunities.detect(profiles, products, txs, TODAY)
    opportunities.prioritize(detected, max_cards=10)
    assert opportunities.counts(detected)["prioritized_today"] <= 10

    opportunities.prioritize(detected, max_cards=2)
    assert opportunities.counts(detected)["prioritized_today"] <= 2
    assert len(opportunities.todays_list(detected)) <= 2


def test_an_empty_dataset_reports_zero_of_both():
    counts = opportunities.counts([])
    assert counts["detected"] == 0
    assert counts["prioritized_today"] == 0
    assert counts["held_back"] == 0


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


def _row(rid, status="New", prioritized=False):
    return {"id": rid, "customer_id": rid, "status": status,
            "prioritized_today": prioritized, "trigger": "due",
            "created_at": TODAY.isoformat(), "influenced_value": 100.0}


def test_funnel_separates_waiting_from_held_back():
    """"Untouched" spans everything detected; the advisor only owes today's list.

    The report used to publish a single "untouched" figure covering every
    detected opportunity, which a screen then labelled as work not yet
    reviewed — implying a backlog five times the size of the actual one.
    """
    from app.analytics import performance as perf

    pipeline = ([_row(f"P{i}", prioritized=True) for i in range(20)]
                + [_row(f"H{i}") for i in range(82)])
    report = perf.report(pipeline, [], as_of=TODAY)

    assert report["opportunities_detected"] == 102
    assert report["prioritized_today"] == 20
    # Only the recommended-and-undecided rows are waiting on a human.
    assert report["awaiting_decision"] == 20
    assert report["detected_not_recommended"] == 82
    # The old total still adds up, so nothing that read it is now wrong.
    assert report["untouched"] == 102


def test_a_decision_leaves_the_waiting_count_and_lands_downstream():
    from app.analytics import performance as perf

    pipeline = [_row("P0", status="Contacted", prioritized=True),
                _row("P1", status="Ignored", prioritized=True),
                *[_row(f"P{i}", prioritized=True) for i in range(2, 20)],
                *[_row(f"H{i}") for i in range(82)]]
    report = perf.report(pipeline, [], as_of=TODAY)

    assert report["awaiting_decision"] == 18
    assert report["open"] == 1
    assert report["ignored"] == 1
    # Every recommendation is in exactly one of those three places.
    assert (report["awaiting_decision"] + report["open"] + report["ignored"]
            == report["prioritized_today"])
    assert report["detected_not_recommended"] == 82


def test_expected_value_reported_is_todays_list_only():
    """The zero-state quotes this figure; it must not include held-back rows."""
    from app.analytics import performance as perf

    pipeline = [_row("P0", prioritized=True), _row("P1", prioritized=True), _row("H0")]
    report = perf.report(pipeline, [], as_of=TODAY)
    assert report["prioritized_expected_value"] == 200.0
