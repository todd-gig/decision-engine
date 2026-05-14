"""
Executive Decision Engine — FastAPI Application

Unified API serving the full decision processing pipeline,
state transitions, learning loop, and static frontend dashboard.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from api.routes import router


logger = logging.getLogger(__name__)

# Env-var seam — operators set this to opt into canonical OutcomeSource
# bootstrap at app startup. Defaults OFF so dev runs never auto-register.
# WHY env-gated: registering rows in ovs_calibration.outcome_sources is
# infrastructure state. Auto-firing on every uvicorn import would
# silently mutate state during dev/test runs. Operator opt-in matches
# the rest of the engine's opt-in flags (CODIFICATION_PROPOSER_ENABLED,
# INTELLIGENCE_SYSTEM_ROUTING, etc.).
PENROSE_BOOTSTRAP_SOURCES_ENV = "PENROSE_BOOTSTRAP_SOURCES"


app = FastAPI(
    title="Executive Decision Engine",
    version="2.0.0",
    description=(
        "Unified decision intelligence engine combining RTQL trust qualification, "
        "value/trust assessment, 7-gate authorization, certificate chain issuance, "
        "state machine lifecycle, and adaptive learning loop into a single "
        "deployable artifact."
    ),
)

app.include_router(router)


def _bootstrap_sources_enabled() -> bool:
    """Return True iff PENROSE_BOOTSTRAP_SOURCES is set to a truthy value.

    Truthy = '1' | 'true' | 'yes' | 'on' (case-insensitive). Anything
    else (including unset, '0', '') = disabled.
    """
    raw = os.environ.get(PENROSE_BOOTSTRAP_SOURCES_ENV, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@app.on_event("startup")
def _maybe_bootstrap_outcome_sources() -> None:
    """Register canonical OutcomeSources at startup when the env flag is set.

    Per `scripts.bootstrap_outcome_sources` docstring, this is the bridge
    between the deployable artifact + the registry table required by the
    Penrose `revenue_per_human_touch` metric. Failure is logged but does
    NOT block app startup (non-blocking is correct here: a healthy
    decision-engine without the registry is still useful for everything
    else; an unhealthy app blocked on registry write is worse).
    """
    if not _bootstrap_sources_enabled():
        return
    try:
        from scripts.bootstrap_outcome_sources import bootstrap_all
        results = bootstrap_all(idempotent=True)
        registered = sum(1 for r in results if r.status == "registered")
        already = sum(1 for r in results if r.status == "already_registered")
        logger.info(
            "penrose bootstrap: %d registered, %d already_registered "
            "(env %s=on)",
            registered, already, PENROSE_BOOTSTRAP_SOURCES_ENV,
        )
    except Exception as exc:  # noqa: BLE001 — startup must not block
        logger.warning(
            "penrose bootstrap failed (non-blocking): %s; "
            "operators can run `python cli.py bootstrap-sources --all` manually",
            exc,
        )

# Serve frontend dashboard
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    @app.get("/dashboard")
    def dashboard():
        return FileResponse(str(frontend_dir / "index.html"))

    @app.get("/input-engine")
    def input_engine():
        return FileResponse(str(frontend_dir / "input-engine.html"))

    # Mount static AFTER explicit routes so they don't shadow API paths
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="static")
