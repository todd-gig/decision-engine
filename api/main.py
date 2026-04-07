"""
Executive Decision Engine — FastAPI Application

Unified API serving the full decision processing pipeline,
state transitions, learning loop, and static frontend dashboard.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from api.routes import router

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
