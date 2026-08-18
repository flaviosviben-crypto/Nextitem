"""DataFrame → JSON conversion that preserves the difference between 0 and unknown.

``NaN`` becomes ``null``, never ``0``. This one rule is what lets the whole
frontend render "Not enough information" instead of a fake zero.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# canonical field -> API key
CAMEL_OVERRIDES = {
    "customer_id": "customerId",
    "product_id": "productId",
    "display_name": "name",
    "product_name": "name",
    "total_spend": "totalSpend",
    "order_count": "orderCount",
    "avg_order_value": "avgOrderValue",
    "recency_days": "recencyDays",
    "tenure_days": "tenureDays",
    "last_purchase_date": "lastPurchase",
    "first_purchase_date": "firstPurchase",
    "expected_cycle_days": "expectedCycleDays",
    "days_overdue": "daysOverdue",
    "cycles_overdue": "cyclesOverdue",
    "next_purchase_due": "nextPurchaseDue",
    "churn_risk": "churnRisk",
    "customer_score": "customerScore",
    "engagement_score": "engagementScore",
    "predicted_12m_value": "predicted12mValue",
    "purchase_velocity": "purchaseVelocity",
    "purchase_regularity": "purchaseRegularity",
    "median_gap_days": "medianGapDays",
    "avg_gap_days": "avgGapDays",
    "discount_rate": "discountRate",
    "avg_discount_pct": "avgDiscountPct",
    "data_confidence": "dataConfidence",
    "segment_reason": "segmentReason",
    "category_affinity": "categoryAffinity",
    "brand_affinity": "brandAffinity",
    "color_affinity": "colorAffinity",
    "size_affinity": "sizeAffinity",
    "price_band_low": "priceBandLow",
    "price_band_high": "priceBandHigh",
    "price_band_mid": "priceBandMid",
    "neutral_color_share": "neutralColorShare",
    "spend_trend": "spendTrend",
    "tx_lines": "transactionLines",
    "purchased_product_ids": "purchasedProductIds",
    "days_in_stock": "daysInStock",
    "days_in_stock_estimated": "daysInStockEstimated",
    "days_since_last_sale": "daysSinceLastSale",
    "age_bucket": "ageBucket",
    "retail_value": "retailValue",
    "cost_value": "costValue",
    "margin_pct": "marginPct",
    "margin_value": "marginValue",
    "unit_margin": "unitMargin",
    "markdown_pct": "markdownPct",
    "sell_through": "sellThrough",
    "weekly_velocity": "weeklyVelocity",
    "weeks_of_cover": "weeksOfCover",
    "units_sold": "unitsSold",
    "units_sold_90d": "unitsSold90d",
    "risk_score": "riskScore",
    "risk_drivers": "riskDrivers",
    "recommended_action": "recommendedAction",
    "arrival_date": "arrivalDate",
    "last_sold_date": "lastSoldDate",
    "avg_selling_price": "avgSellingPrice",
    "original_price": "originalPrice",
    "score_coverage": "scoreCoverage",
    "primary_store": "primaryStore",
    "preferred_categories": "preferredCategories",
    "preferred_brands": "preferredBrands",
    "spend_recent_180d": "spendRecent180d",
    "spend_prior_180d": "spendPrior180d",
    "max_line_value": "maxLineValue",
    "net_amount": "netAmount",
    "unit_price": "unitPrice",
    "transaction_id": "transactionId",
    "discount_sensitivity": "discountSensitivity",
}

# never serialised to the client on list endpoints
INTERNAL_COLUMNS = {"_appeal"}


def camel(name: str) -> str:
    if name in CAMEL_OVERRIDES:
        return CAMEL_OVERRIDES[name]
    parts = name.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def clean_value(value: Any) -> Any:
    """Convert one cell to a JSON-safe value, keeping unknowns as ``None``."""
    if value is None:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if np.isnan(number) or np.isinf(number):
            return None
        return round(number, 4)
    if isinstance(value, (pd.Timestamp,)):
        return None if pd.isna(value) else value.strftime("%Y-%m-%d")
    if value is pd.NaT:
        return None
    if isinstance(value, (np.ndarray,)):
        return [clean_value(v) for v in value.tolist()]
    if isinstance(value, list):
        return [clean_value(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_value(v) for k, v in value.items()}
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def row_to_dict(row: pd.Series, fields: list[str] | None = None) -> dict[str, Any]:
    keys = fields if fields is not None else [k for k in row.index if k not in INTERNAL_COLUMNS]
    return {camel(key): clean_value(row.get(key)) for key in keys if key in row.index}


def frame_to_records(frame: pd.DataFrame, fields: list[str] | None = None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    columns = [c for c in (fields or frame.columns) if c in frame.columns
               and c not in INTERNAL_COLUMNS]
    subset = frame[columns]
    return [
        {camel(col): clean_value(value) for col, value in zip(columns, values)}
        for values in subset.itertuples(index=False, name=None)
    ]
