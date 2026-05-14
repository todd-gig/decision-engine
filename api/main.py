"""
Executive Decision Engine — FastAPI Application

Unified API serving the full decision processing pipeline,
state transitions, learning loop, and static frontend dashboard.
"""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from api.routes import router

logger = logging.getLogger(__name__)

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


# ── PPEME Master Calculator bootstrap ───────────────────────────────────────
#
# Builds the singleton on app startup so the Penrose BFT emitter is ready
# to receive `finalize_participant_state` calls. Env-driven (see
# ppeme.master_calculator._build_from_env); absent URL → dry_run mode.
@app.on_event("startup")
def _bootstrap_master_calculator() -> None:
    try:
        from ppeme.master_calculator import get_master_calculator
        calc = get_master_calculator()
        logger.info(
            "ppeme.master_calculator: bootstrapped (emitter.url=%s)",
            calc.emitter._scoreboard_url or "<dry_run>",
        )
    except Exception as exc:  # noqa: BLE001
        # Always-online priority: never block app startup on PPEME bootstrap.
        logger.warning(
            "ppeme.master_calculator bootstrap failed (non-fatal): %s", exc,
        )


@app.on_event("shutdown")
def _shutdown_master_calculator() -> None:
    try:
        from ppeme.master_calculator import get_master_calculator
        get_master_calculator().shutdown(wait=False)
    except Exception:  # noqa: BLE001
        pass

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
