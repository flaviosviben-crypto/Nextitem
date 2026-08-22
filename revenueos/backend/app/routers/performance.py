"""Performance: did acting on RevenueOS produce revenue?"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..analytics import performance as perf
from ..workspace import workspace

router = APIRouter(tags=["performance"])


@router.get("/performance")
def performance_report(window_days: int = Query(30, ge=7, le=365),
                       advisor: str = "", store: str = "") -> dict[str, Any]:
    """The Performance page: page-wide totals plus the advisor/store/channel/
    reason breakdown tables it extends, all narrowed to the same optional
    advisor or store filter.

    ``as_of`` is always the workspace's own snapshot date, explicitly — never
    left for ``perf.report`` to infer from whatever transactions a filter
    happens to leave behind, which would let "today" quietly shift as an
    advisor or store is selected.
    """
    report = perf.report(workspace.pipeline, workspace.transactions_raw,
                         as_of=workspace.as_of, window_days=window_days,
                         profiles=workspace.profiles,
                         advisor=advisor or None, store=store or None)
    return {
        **report,
        "loaded": workspace.is_loaded,
        # The honest caveat travels with the numbers rather than sitting in a
        # footnote nobody reads.
        "attribution_note": report["measurement_caveat"],
    }
