"""
api/routes/chat.py — Chat endpoints.

POST /chat/sessions          — create session
GET  /chat/sessions/{id}     — get session
GET  /chat/sessions/user/{uid} — list user sessions
POST /chat/message           — send message (non-streaming)
POST /chat/message/stream    — send message (SSE streaming)
"""

from __future__ import annotations
import json
import time
import uuid
from datetime import datetime
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.models import (
    ChatRequest, ChatResponse, ChatMessage, MessageRole,
    SessionCreateRequest, SessionResponse, AIProvider, StreamChunk,
)
import api.session_store as store
import api.engine_middleware as engine
from api.translation import get_encoder
from api.providers import get_provider

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Session management ────────────────────────────────────────────────────────

@router.post("/sessions", response_model=SessionResponse)
async def create_session(req: SessionCreateRequest):
    session = store.create_session(
        user_id=req.user_id,
        entity_context=req.entity_context,
        preferred_provider=req.preferred_provider,
    )
    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        entity_context=session.entity_context,
        preferred_provider=session.preferred_provider,
        message_count=0,
        created_at=session.created_at,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        entity_context=session.entity_context,
        preferred_provider=session.preferred_provider,
        message_count=len(session.messages),
        created_at=session.created_at,
    )


@router.get("/sessions/user/{user_id}", response_model=list[SessionResponse])
async def list_user_sessions(user_id: str):
    sessions = store.list_sessions_for_user(user_id)
    return [
        SessionResponse(
            session_id=s.session_id,
            user_id=s.user_id,
            entity_context=s.entity_context,
            preferred_provider=s.preferred_provider,
            message_count=len(s.messages),
            created_at=s.created_at,
        )
        for s in sessions
    ]


# ── Message (non-streaming) ───────────────────────────────────────────────────

@router.post("/message", response_model=ChatResponse)
async def send_message(req: ChatRequest):
    session = store.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    provider_choice = req.provider or session.preferred_provider
    t0 = time.time()

    # 1. Pre-process through decision engine
    insight = engine.process(req.message, session)

    # 2. Store the user message with engine insight
    user_msg = ChatMessage(
        role=MessageRole.USER,
        content=req.message,
        timestamp=datetime.utcnow(),
        engine_insight=insight,
    )
    store.append_message(req.session_id, user_msg)

    # 3. Encode for provider (Speech 101 translation layer)
    encoder = get_encoder(provider_choice)
    encoded = encoder.encode(
        user_message=req.message,
        engine_insight=insight,
        history=session.messages[:-1],  # exclude the message we just appended
        entity_context=session.entity_context,
    )

    # 4. Send to provider
    provider = get_provider(provider_choice)
    response_text = await provider.complete(encoded)

    # 5. Store assistant response
    assistant_msg = ChatMessage(
        role=MessageRole.ASSISTANT,
        content=response_text,
        provider=provider_choice,
        timestamp=datetime.utcnow(),
    )
    store.append_message(req.session_id, assistant_msg)

    latency_ms = int((time.time() - t0) * 1000)

    return ChatResponse(
        session_id=req.session_id,
        message_id=str(uuid.uuid4()),
        content=response_text,
        provider=provider_choice,
        engine_insight=insight,
        latency_ms=latency_ms,
    )


# ── Message (SSE streaming) ───────────────────────────────────────────────────

@router.post("/message/stream")
async def stream_message(req: ChatRequest):
    session = store.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    provider_choice = req.provider or session.preferred_provider

    # Pre-process through decision engine
    insight = engine.process(req.message, session)

    # Store user message
    user_msg = ChatMessage(
        role=MessageRole.USER,
        content=req.message,
        timestamp=datetime.utcnow(),
        engine_insight=insight,
    )
    store.append_message(req.session_id, user_msg)

    # Encode
    encoder = get_encoder(provider_choice)
    encoded = encoder.encode(
        user_message=req.message,
        engine_insight=insight,
        history=session.messages[:-1],
        entity_context=session.entity_context,
    )

    provider = get_provider(provider_choice)

    async def event_stream() -> AsyncIterator[str]:
        # First: emit engine insight so the UI can display it immediately
        insight_chunk = StreamChunk(type="engine_insight", data=insight.model_dump())
        yield f"data: {insight_chunk.model_dump_json()}\n\n"

        # Stream the AI response
        full_response = []
        try:
            async for text_chunk in provider.stream(encoded):
                full_response.append(text_chunk)
                content_chunk = StreamChunk(type="content", data=text_chunk)
                yield f"data: {content_chunk.model_dump_json()}\n\n"
        except Exception as e:
            error_chunk = StreamChunk(type="error", data=str(e))
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            return

        # Persist completed assistant message
        complete_text = "".join(full_response)
        assistant_msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=complete_text,
            provider=provider_choice,
            timestamp=datetime.utcnow(),
        )
        store.append_message(req.session_id, assistant_msg)

        done_chunk = StreamChunk(type="done", data={"message_id": str(uuid.uuid4())})
        yield f"data: {done_chunk.model_dump_json()}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
