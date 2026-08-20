"""RevenueOS API."""
from __future__ import annotations

import logging
import os
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import (
    analyst, campaigns, customers, data, opportunities, outreach, overview, performance,
    products, scenarios,
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
               opportunities.router, outreach.router, performance.router,
               analyst.router, campaigns.router, scenarios.router):
    app.include_router(router, prefix="/api")


# Startup state, reported by /api/health rather than raised. See _startup.
STARTUP_ERROR: str | None = None
_LOADING = False


def _load_data() -> None:
    """Restore or seed the workspace. Runs off the startup path — see _startup."""
    global STARTUP_ERROR, _LOADING
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
    finally:
        _LOADING = False


@app.on_event("startup")
def _startup() -> None:
    """Start serving immediately; load data behind the running server.

    Two failure modes are being avoided here, both of which end with a hosting
    platform returning a bare 502 that explains nothing.

    Uvicorn serves no request at all — not even the health check — until this
    event returns. Rebuilding the analytics pipeline takes a couple of seconds
    on a developer machine and far longer on a throttled shared instance, so
    doing it inline risks the platform's health check timing out and marking an
    otherwise healthy deploy as failed.

    And an exception raised here aborts startup entirely, leaving no routes and
    no way for the service to report its own failure. Loading data is
    best-effort work: it belongs on a thread, with its outcome recorded.
    """
    global _LOADING
    _LOADING = True
    threading.Thread(target=_load_data, name="revenueos-load", daemon=True).start()


@app.get("/api/health")
def health() -> dict[str, object]:
    """Never fails. The platform decides whether a deploy succeeded from this.

    If this endpoint can raise, a deploy can be marked failed for a reason that
    has nothing to do with whether the API works — and a failed deploy is served
    as a gateway error with no explanation.
    """
    try:
        from .ai.client import status as ai_status
        ai: object = ai_status()
    except Exception as exc:  # noqa: BLE001
        ai = {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    return {
        # loading  — serving, data still being built behind the server
        # degraded — serving, but the load failed and startup_error says why
        # ok       — serving normally
        "status": "degraded" if STARTUP_ERROR else "loading" if _LOADING else "ok",
        "startup_error": STARTUP_ERROR,
        "loading": _LOADING,
        "loaded": workspace.is_loaded,
        "source": workspace.source,
        "computed_at": workspace.computed_at,
        "ai": ai,
    }
