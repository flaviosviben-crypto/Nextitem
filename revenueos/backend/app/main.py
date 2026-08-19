"""RevenueOS API."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import (
    analyst, campaigns, customers, data, opportunities, overview, performance, products,
    scenarios,
)
from .workspace import workspace

app = FastAPI(
    title="RevenueOS API",
    description="AI revenue intelligence for fashion boutiques.",
    version="1.0.0",
)

def _origins() -> list[str]:
    """Allowed origins, tolerating a bare hostname.

    Hosting platforms expose their services as hostnames rather than full
    origins. A bare host would silently never match a browser Origin header, so
    give it the scheme it is missing rather than failing quietly.
    """
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    out = []
    for item in raw.split(","):
        item = item.strip()
        if item and "://" not in item:
            item = f"https://{item}"
        if item:
            out.append(item)
    return out


app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The V1 surface is data, customers, products, opportunities and performance.
# Analyst, campaigns and scenarios stay mounted: the intelligence is preserved
# and reachable by API, it simply no longer has a place in the primary navigation.
for router in (data.router, overview.router, customers.router, products.router,
               opportunities.router, performance.router, analyst.router, campaigns.router, scenarios.router):
    app.include_router(router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    """Restore the last workspace so a restart does not lose the boutique's data."""
    if workspace.is_loaded:
        return
    if workspace.load():
        return
    # Nothing to restore. On a host with an ephemeral filesystem that is the
    # normal state after every deploy, which would leave a public URL showing an
    # empty shell. Opt in per environment: unset means the local behaviour of
    # starting empty and waiting for an import is unchanged.
    if os.environ.get("SEED_DEMO_ON_EMPTY", "").strip().lower() in {"1", "true", "yes"}:
        workspace.load_demo()


@app.get("/api/health")
def health() -> dict[str, object]:
    from .ai.client import status as ai_status
    return {
        "status": "ok",
        "loaded": workspace.is_loaded,
        "source": workspace.source,
        "computed_at": workspace.computed_at,
        "ai": ai_status(),
    }
