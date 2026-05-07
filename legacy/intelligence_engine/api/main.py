"""
api/main.py — Gigaton AI Gateway

FastAPI application. Runs on port 8002 (matches existing gigaton-ui-system apiClient config).

Architecture:
  User message
    → Decision Engine (pre-AI processing: intent, context, trust tier)
    → Translation Layer (provider-specific encoding — Speech 101 principle)
    → AI Provider (Claude | OpenAI | Gemini)
    → Streaming response → Chat UI

Run:
  uvicorn api.main:app --host 0.0.0.0 --port 8002 --reload

  (from intelligence-engine/ root, with PYTHONPATH set)
  PYTHONPATH=. uvicorn api.main:app --port 8002 --reload
"""

from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.models import HealthResponse
from api.routes.chat import router as chat_router
from api.providers import available_providers

app = FastAPI(
    title="Gigaton AI Gateway",
    description=(
        "Decision engine-augmented AI chat API. "
        "Every message is pre-processed by the Gigaton decision engine before "
        "being encoded and routed to the configured AI provider."
    ),
    version="1.0.0",
)

# Allow the Vite dev server (port 5173) and production origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://gigaton.ai",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health", response_model=HealthResponse)
async def health():
    providers = available_providers()
    return HealthResponse(
        status="ok",
        engine="gigaton-decision-engine-v3.2",
        providers_available=providers if providers else ["mock"],
    )


@app.get("/")
async def root():
    return {
        "service": "Gigaton AI Gateway",
        "version": "1.0.0",
        "docs": "/docs",
    }
