"""RevenueOS API."""
from __future__ import annotations

import logging
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


# Recorded rather than raised, and surfaced by /api/health. See _startup.
STARTUP_ERROR: str | None = None


@app.on_event("startup")
def _startup() -> None:
    """Restore the last workspace, or seed one, without ever being able to
    take the service down.

    An exception raised here aborts uvicorn's startup entirely: no routes, no
    health check, and a hosting platform answers every request with a bare 502.
    Loading data is best-effort work — a corrupt snapshot or a failed seed must
    leave an empty but *running* API that can say what went wrong, not a dead
    one that cannot.
    """
    global STARTUP_ERROR
    try:
        if workspace.is_loaded:
            return
        if workspace.load():
            return
        # Nothing to restore. On a host with an ephemeral filesystem that is the
        # normal state after every deploy, which would leave a public URL showing
        # an empty shell. Opt in per environment: unset means the local behaviour
        # of starting empty and waiting for an import is unchanged.
        if os.environ.get("SEED_DEMO_ON_EMPTY", "").strip().lower() in {"1", "true", "yes"}:
            workspace.load_demo()
    except Exception as exc:  # noqa: BLE001 - deliberately total
        STARTUP_ERROR = f"{type(exc).__name__}: {exc}"
        logging.getLogger("revenueos").exception("Startup data load failed")
        try:
            workspace.reset()
        except Exception:  # noqa: BLE001
            pass


@app.get("/api/health")
def health() -> dict[str, object]:
    from .ai.client import status as ai_status
    return {
        # "degraded" means the API is serving but has no data because loading
        # failed. A caller can tell that apart from an empty boutique.
        "status": "degraded" if STARTUP_ERROR else "ok",
        "startup_error": STARTUP_ERROR,
        "loaded": workspace.is_loaded,
        "source": workspace.source,
        "computed_at": workspace.computed_at,
        "ai": ai_status(),
    }
