"""Turn mapped raw rows into typed, normalised records.

Rules that matter commercially:
  * an absent value becomes ``None`` — never 0, never "Unknown" masquerading as data
  * labels (category/brand/colour/size) are normalised so the same thing groups together
  * derived values are only computed when their inputs genuinely exist
"""
from __future__ import annotations

from typing import Any, Iterable

from .values import (
    clean_label,
    clean_text,
    normalize_color,
    normalize_size,
    parse_bool,
    parse_date,
    parse_number,
    parse_rate,
)

_LABEL_FIELDS = {"category", "subcategory", "brand", "city", "country", "store", "season",
                 "collection", "supplier", "channel", "segment", "gender", "preferred_category",
                 "preferred_brand", "advisor", "product", "product_name", "description", "notes"}
_MONEY_FIELDS = {"total_spend", "avg_order_value", "unit_price", "line_total", "price",
                 "original_price", "cost", "discount"}
_NUMBER_FIELDS = {"num_purchases", "quantity", "stock", "age", "margin", "discount_sensitivity"}
_DATE_FIELDS = {"last_purchase_date", "first_purchase_date", "birth_date", "date", "arrival_date"}
_BOOL_FIELDS = {"marketing_consent"}


def _coerce(field: str, raw: object) -> Any:
    if field in _DATE_FIELDS:
        return parse_date(raw)
    if field in _BOOL_FIELDS:
        return parse_bool(raw)
    if field == "size":
        return normalize_size(raw)
    if field == "color":
        return normalize_color(raw)
    if field in {"discount_sensitivity", "margin"}:
        return parse_rate(raw)
    if field in _MONEY_FIELDS or field in _NUMBER_FIELDS:
        return parse_number(raw)
    if field in _LABEL_FIELDS:
        return clean_label(raw)
    return clean_text(raw)


def _row_to_record(row: dict[str, str], mapping: dict[str, str]) -> dict[str, Any]:
    return {field: _coerce(field, row.get(header)) for field, header in mapping.items()}


def build_customers(rows: Iterable[dict[str, str]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        rec = _row_to_record(row, mapping)

        name = rec.get("name")
        if not name:
            parts = [rec.get("first_name"), rec.get("last_name")]
            name = " ".join(p for p in parts if p) or None
        cid = rec.get("customer_id") or rec.get("email") or (name and f"NAME::{name}")
        if not cid:
            continue  # a customer we cannot identify at all is not usable
        rec["customer_id"] = str(cid).strip()
        rec["name"] = name or str(cid)

        # AOV can be derived, but only when both inputs are real.
        spend, orders = rec.get("total_spend"), rec.get("num_purchases")
        if rec.get("avg_order_value") is None and spend is not None and orders:
            rec["avg_order_value"] = spend / orders
        if spend is None and rec.get("avg_order_value") is not None and orders:
            rec["total_spend"] = rec["avg_order_value"] * orders

        rec["_row"] = i
        out.append(rec)
    return out


def build_transactions(rows: Iterable[dict[str, str]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        rec = _row_to_record(row, mapping)
        cid = rec.get("customer_id")
        if not cid:
            continue
        rec["customer_id"] = str(cid).strip()

        qty = rec.get("quantity")
        unit = rec.get("unit_price")
        total = rec.get("line_total")
        discount = rec.get("discount")

        if total is None and unit is not None:
            total = unit * (qty if qty else 1)
            if discount is not None:
                # A discount below 1 is a rate; above 1 it is an absolute amount.
                total = total * (1 - discount) if 0 < discount < 1 else max(0.0, total - discount)
        if unit is None and total is not None and qty:
            unit = total / qty
        if total is None:
            continue  # a line with no money in it cannot drive revenue analytics

        rec["quantity"] = qty if qty is not None else 1
        rec["unit_price"] = unit
        rec["line_total"] = max(0.0, float(total))
        rec["transaction_id"] = str(rec.get("transaction_id") or f"TX-{i + 1}")
        rec["sku"] = str(rec["sku"]).strip() if rec.get("sku") else None
        rec["_row"] = i
        out.append(rec)
    return out


def build_inventory(rows: Iterable[dict[str, str]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows):
        rec = _row_to_record(row, mapping)
        sku = rec.get("sku") or rec.get("product_id")
        name = rec.get("product_name") or rec.get("product")
        if not sku and not name:
            continue
        sku = str(sku or f"SKU-{i + 1}").strip()
        rec["sku"] = sku
        rec["product_name"] = name or sku

        price, original, cost = rec.get("price"), rec.get("original_price"), rec.get("cost")
        if rec.get("margin") is None and price and cost is not None and price > 0:
            rec["margin"] = (price - cost) / price
        if original and price and original > price:
            rec["markdown_rate"] = (original - price) / original
        else:
            rec["markdown_rate"] = None

        rec["_row"] = i

        # Size/colour variants of one SKU collapse into a single stock position.
        if sku in seen:
            prior = seen[sku]
            if rec.get("stock") is not None:
                prior["stock"] = (prior.get("stock") or 0) + rec["stock"]
            for key, val in rec.items():
                if prior.get(key) is None and val is not None and key != "stock":
                    prior[key] = val
            continue
        seen[sku] = rec
        out.append(rec)
    return out


BUILDERS = {
    "customers": build_customers,
    "transactions": build_transactions,
    "inventory": build_inventory,
}
