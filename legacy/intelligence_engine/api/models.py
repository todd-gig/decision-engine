"""
api/models.py — Shared data contracts for the Gigaton AI Gateway.

All structures crossing the HTTP boundary are defined here.
The translation layer and providers both consume these — never import
directly from the intelligence engine's own models at the API boundary.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ── Provider Registry ─────────────────────────────────────────────────────────

class AIProvider(str, Enum):
    CLAUDE  = "claude"
    OPENAI  = "openai"
    GEMINI  = "gemini"


# ── Engine Insight (pre-AI processing result) ─────────────────────────────────

class EngineInsight(BaseModel):
    """
    What the decision engine determined about this message BEFORE
    it was sent to any AI provider.

    This is the output of the pre-AI processing pipeline and becomes
    part of the context injected into each provider's encoded prompt.
    """
    intent_type: str                        # classified intent of the user's message
    intent_confidence: float                # 0.0 – 1.0
    entity_context: str                     # which Gigaton entity this relates to
    relevant_domain: str                    # e.g. "pricing", "lead_scoring", "general"
    trust_tier: str                         # T0–T4 from RTQL pipeline
    suggested_depth: str                    # "brief" | "detailed" | "analytical"
    engine_notes: list[str]                 # explicit notes for the AI to incorporate
    raw_score: float                        # net value score from pipeline


# ── Session ───────────────────────────────────────────────────────────────────

class MessageRole(str, Enum):
    USER      = "user"
    ASSISTANT = "assistant"
    SYSTEM    = "system"


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    provider: Optional[AIProvider] = None
    engine_insight: Optional[EngineInsight] = None  # set on user messages after processing


class ConversationSession(BaseModel):
    session_id: str
    user_id: str
    entity_context: str = "gigaton"             # which entity this session belongs to
    preferred_provider: AIProvider = AIProvider.CLAUDE
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Request / Response ────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    message: str
    provider: Optional[AIProvider] = None      # None = use session preferred_provider
    entity_context: Optional[str] = None       # override entity context for this message
    stream: bool = True


class ChatResponse(BaseModel):
    session_id: str
    message_id: str
    role: MessageRole = MessageRole.ASSISTANT
    content: str
    provider: AIProvider
    engine_insight: EngineInsight
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None


class StreamChunk(BaseModel):
    """Emitted over SSE during streaming responses."""
    type: str           # "content" | "engine_insight" | "done" | "error"
    data: Any


class SessionCreateRequest(BaseModel):
    user_id: str
    entity_context: str = "gigaton"
    preferred_provider: AIProvider = AIProvider.CLAUDE


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    entity_context: str
    preferred_provider: AIProvider
    message_count: int
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    engine: str
    providers_available: list[str]
    version: str = "1.0.0"
