"""Performance: did acting on RevenueOS produce revenue?"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..analytics import performance as perf
from ..workspace import workspace

router = APIRouter(tags=["performance"])


@router.get("/performance")
def performance_report(window_days: int = Query(30, ge=7, le=365)) -> dict[str, Any]:
    report = perf.report(workspace.pipeline, workspace.transactions_raw,
                         window_days=window_days)
    return {
        **report,
        "loaded": workspace.is_loaded,
        # The honest caveat travels with the numbers rather than sitting in a
        # footnote nobody reads.
        "attribution_note": report["measurement_caveat"],
    }
