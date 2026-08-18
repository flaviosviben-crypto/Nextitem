"""Apply a column mapping and produce canonical, typed, deduplicated tables.

Design rule that runs through this whole module: **absence is recorded as
absence**. A missing price becomes ``NaN``, never ``0``. Downstream analytics
can then distinguish "this product is free" from "we do not know the price",
which is what stops the product from inventing fake zeros.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .ingestion import to_numeric_series
from .parsing import (
    normalise_color,
    normalise_gender,
    normalise_label,
    normalise_size,
    split_list,
    to_date_series,
)
from .schema import ENTITIES, Kind

_ID_CLEAN_RE = re.compile(r"\.0$")


@dataclass
class CleanReport:
    entity: str
    rows_in: int
    rows_out: int
    dropped_missing_key: int = 0
    dropped_duplicates: int = 0
    coerced: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "rowsIn": self.rows_in,
            "rowsOut": self.rows_out,
            "droppedMissingKey": self.dropped_missing_key,
            "droppedDuplicates": self.dropped_duplicates,
            "coerced": self.coerced,
            "notes": self.notes,
        }


def _clean_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        if np.isnan(value):
            return None
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return None
    text = _ID_CLEAN_RE.sub("", text)  # 10023.0 -> 10023 (Excel float coercion)
    return text


def apply_mapping(frame: pd.DataFrame, entity_name: str,
                  field_map: dict[str, str]) -> tuple[pd.DataFrame, CleanReport]:
    """Project a raw frame onto the canonical schema and coerce types.

    ``field_map`` maps ``canonical_field -> source_column``. Unknown fields and
    columns that are absent from the frame are ignored, so a partially-mapped
    file still yields a usable table.
    """
    ent = ENTITIES[entity_name]
    fields = ent.field_map()
    report = CleanReport(entity=entity_name, rows_in=len(frame), rows_out=0)

    out = pd.DataFrame(index=frame.index)
    for canonical, source in field_map.items():
        if canonical not in fields or source not in frame.columns:
            continue
        spec = fields[canonical]
        column = frame[source]
        if spec.kind is Kind.ID:
            out[canonical] = column.map(_clean_id)
        elif spec.kind is Kind.DATE:
            out[canonical] = to_date_series(column)
        elif spec.is_numeric:
            numeric = to_numeric_series(column)
            failed = int(column.notna().sum() - numeric.notna().sum())
            if failed > 0:
                report.coerced[canonical] = failed
            out[canonical] = numeric
        elif spec.kind is Kind.LIST:
            out[canonical] = column.map(split_list)
        elif spec.kind is Kind.CATEGORY:
            if canonical == "color":
                out[canonical] = column.map(normalise_color)
            elif canonical == "size":
                out[canonical] = column.map(normalise_size)
            elif canonical == "gender":
                out[canonical] = column.map(normalise_gender)
            else:
                out[canonical] = column.map(normalise_label)
        elif spec.kind is Kind.EMAIL:
            out[canonical] = column.map(
                lambda v: str(v).strip().lower() if v is not None and str(v).strip() else None
            )
        else:
            out[canonical] = column.map(
                lambda v: str(v).strip() if v is not None and str(v).strip() else None
            )

    for name in fields:
        if name not in out.columns:
            out[name] = pd.Series([None] * len(out), index=out.index, dtype="object")

    out = out[[f.name for f in ent.fields]]
    if entity_name == "customers":
        out, report = _clean_customers(out, report)
    elif entity_name == "transactions":
        out, report = _clean_transactions(out, report)
    else:
        out, report = _clean_inventory(out, report)

    report.rows_out = len(out)
    return out.reset_index(drop=True), report


# --------------------------------------------------------------------------- #
# per-entity rules
# --------------------------------------------------------------------------- #
def _compose_name(row: pd.Series) -> str | None:
    full = row.get("full_name")
    if isinstance(full, str) and full.strip():
        return " ".join(full.split())
    parts = [row.get("first_name"), row.get("last_name")]
    parts = [str(p).strip() for p in parts if isinstance(p, str) and p.strip()]
    if parts:
        return " ".join(parts)
    return None


def _clean_customers(frame: pd.DataFrame, report: CleanReport) -> tuple[pd.DataFrame, CleanReport]:
    frame = frame.copy()
    frame["display_name"] = frame.apply(_compose_name, axis=1)

    if frame["customer_id"].isna().all():
        # Synthesise stable keys so the dataset stays usable, and say so.
        basis = frame["email"].fillna(frame["display_name"]).fillna(
            pd.Series([f"row-{i}" for i in range(len(frame))], index=frame.index)
        )
        frame["customer_id"] = [
            f"C{abs(hash(str(v))) % 10**8:08d}" for v in basis
        ]
        report.notes.append(
            "No customer identifier column was found — stable synthetic IDs were "
            "generated from email/name so analytics can still run."
        )
    else:
        missing = frame["customer_id"].isna()
        if missing.any():
            report.dropped_missing_key = int(missing.sum())
            frame = frame[~missing]
            report.notes.append(
                f"{report.dropped_missing_key} row(s) had no customer ID and were skipped."
            )

    before = len(frame)
    frame = frame.drop_duplicates(subset=["customer_id"], keep="first")
    report.dropped_duplicates = before - len(frame)
    if report.dropped_duplicates:
        report.notes.append(
            f"{report.dropped_duplicates} duplicate customer ID(s) collapsed to one row each."
        )

    if frame["display_name"].isna().any():
        frame["display_name"] = frame.apply(
            lambda r: r["display_name"] or f"Customer {r['customer_id']}", axis=1
        )
    return frame, report


def _clean_transactions(frame: pd.DataFrame, report: CleanReport) -> tuple[pd.DataFrame, CleanReport]:
    frame = frame.copy()

    if "quantity" in frame:
        qty = frame["quantity"]
        frame["quantity"] = qty.where(qty.notna() & (qty != 0), other=np.nan)

    # Reconstruct the money column from whatever is available, but only from
    # real inputs — never default to zero.
    net = frame.get("net_amount")
    unit = frame.get("unit_price")
    qty = frame.get("quantity")
    discount = frame.get("discount")

    if net is None or net.isna().all():
        if unit is not None and not unit.isna().all():
            quantity = qty.fillna(1) if qty is not None else 1
            computed = unit * quantity
            if discount is not None and not discount.isna().all():
                # discount stored either as a percentage (<=100) or an amount
                as_pct = discount.where(discount.between(0, 100), other=np.nan) / 100.0
                computed = np.where(
                    as_pct.notna(), computed * (1 - as_pct.fillna(0)), computed - discount.fillna(0)
                )
                computed = pd.Series(computed, index=frame.index)
            frame["net_amount"] = computed
            report.notes.append(
                "Line totals were reconstructed from unit price, quantity and discount."
            )
        else:
            report.notes.append(
                "No monetary column was detected — revenue analytics will be unavailable."
            )

    if frame["net_amount"].notna().any():
        # negative lines are returns: keep them, they are real signal
        returns = int((frame["net_amount"] < 0).sum())
        if returns:
            report.notes.append(f"{returns} negative line(s) treated as returns/refunds.")

    missing_customer = frame["customer_id"].isna()
    if missing_customer.any():
        report.dropped_missing_key = int(missing_customer.sum())
        report.notes.append(
            f"{report.dropped_missing_key} transaction(s) had no customer ID — they still "
            "count towards product performance but not towards any customer profile."
        )

    if frame["date"].notna().any():
        future = frame["date"] > (pd.Timestamp.now() + pd.Timedelta(days=1))
        if future.any():
            report.notes.append(
                f"{int(future.sum())} transaction date(s) are in the future and were kept but flagged."
            )

    before = len(frame)
    subset = [c for c in ("transaction_id", "customer_id", "product_id", "date", "net_amount")
              if c in frame.columns and frame[c].notna().any()]
    if subset:
        frame = frame.drop_duplicates(subset=subset, keep="first")
    report.dropped_duplicates = before - len(frame)
    if frame["quantity"].isna().all():
        frame["quantity"] = 1.0
        report.notes.append("Quantity was not provided — each line counted as 1 unit.")
    return frame, report


def _clean_inventory(frame: pd.DataFrame, report: CleanReport) -> tuple[pd.DataFrame, CleanReport]:
    frame = frame.copy()

    if frame["product_id"].isna().all():
        source = frame["sku"] if frame["sku"].notna().any() else frame["product_name"]
        if source.notna().any():
            frame["product_id"] = source.map(
                lambda v: f"P{abs(hash(str(v))) % 10**8:08d}" if v is not None else None
            )
            report.notes.append("Product IDs were derived from SKU/name.")
        else:
            frame["product_id"] = [f"P{i:08d}" for i in range(len(frame))]
            report.notes.append("Product IDs were generated by row position.")
    missing = frame["product_id"].isna()
    if missing.any():
        report.dropped_missing_key = int(missing.sum())
        frame = frame[~missing]

    before = len(frame)
    frame = frame.drop_duplicates(subset=["product_id"], keep="first")
    report.dropped_duplicates = before - len(frame)

    if frame["stock"].notna().any():
        negative = frame["stock"] < 0
        if negative.any():
            report.notes.append(
                f"{int(negative.sum())} product(s) have negative stock — treated as 0 on hand."
            )
            frame.loc[negative, "stock"] = 0.0

    # margin can be derived when cost is present; otherwise it stays unknown
    if frame["margin"].isna().all() and frame["cost"].notna().any() and frame["price"].notna().any():
        with np.errstate(divide="ignore", invalid="ignore"):
            derived = (frame["price"] - frame["cost"]) / frame["price"].replace(0, np.nan)
        frame["margin"] = (derived * 100).where(derived.notna())
        report.notes.append("Margin % derived from price and cost.")
    elif frame["margin"].notna().any():
        # normalise 0.62 -> 62%
        margins = frame["margin"]
        if margins.dropna().le(1.0).mean() > 0.8:
            frame["margin"] = margins * 100

    if frame["product_name"].isna().any():
        frame["product_name"] = frame.apply(
            lambda r: r["product_name"] or (r["sku"] or f"Product {r['product_id']}"), axis=1
        )
    return frame, report


def deduplicate_customers(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Detect *likely* duplicate customers (same email, or same name + city).

    Duplicates are reported, not merged: merging customer records is a business
    decision with GDPR implications, so the product surfaces the evidence and
    lets the owner decide.
    """
    groups: list[dict[str, Any]] = []
    if frame.empty:
        return frame, groups

    if "email" in frame and frame["email"].notna().any():
        by_email = frame[frame["email"].notna()].groupby("email")
        for email, rows in by_email:
            if len(rows) > 1:
                groups.append({
                    "reason": "identical email address",
                    "key": str(email),
                    "customerIds": rows["customer_id"].tolist(),
                    "names": [n for n in rows.get("display_name", pd.Series(dtype=object)).tolist() if n],
                })

    if "display_name" in frame and frame["display_name"].notna().any():
        keyed = frame.assign(
            _k=frame["display_name"].str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
            + "|" + frame.get("city", pd.Series([""] * len(frame), index=frame.index)).fillna("").astype(str).str.lower()
        )
        for key, rows in keyed[keyed["_k"].notna()].groupby("_k"):
            if len(rows) > 1 and key.strip(" |"):
                ids = rows["customer_id"].tolist()
                if any(set(ids) == set(g["customerIds"]) for g in groups):
                    continue
                groups.append({
                    "reason": "same name and city",
                    "key": key.split("|")[0].title(),
                    "customerIds": ids,
                    "names": [n for n in rows["display_name"].tolist() if n],
                })
    return frame, groups[:50]
