"""
api/session_store.py — In-memory + SQLite-backed session management.

Keeps conversation history per user so the engine has prior-turn context
when building engine insights. SQLite is the persistence layer so sessions
survive restarts. In-memory dict is the hot path.
"""

from __future__ import annotations
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from api.models import (
    ConversationSession, ChatMessage, MessageRole, AIProvider
)

DB_PATH = Path(__file__).parent.parent / "data" / "sessions.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id       TEXT PRIMARY KEY,
                user_id          TEXT NOT NULL,
                entity_context   TEXT NOT NULL DEFAULT 'gigaton',
                preferred_provider TEXT NOT NULL DEFAULT 'claude',
                messages_json    TEXT NOT NULL DEFAULT '[]',
                metadata_json    TEXT NOT NULL DEFAULT '{}',
                created_at       TEXT NOT NULL,
                last_active      TEXT NOT NULL
            )
        """)
        conn.commit()


# Initialise on import
_init_db()

# Hot cache: session_id → ConversationSession
_cache: dict[str, ConversationSession] = {}


def create_session(
    user_id: str,
    entity_context: str = "gigaton",
    preferred_provider: AIProvider = AIProvider.CLAUDE,
) -> ConversationSession:
    session_id = str(uuid.uuid4())
    now = datetime.utcnow()
    session = ConversationSession(
        session_id=session_id,
        user_id=user_id,
        entity_context=entity_context,
        preferred_provider=preferred_provider,
        created_at=now,
        last_active=now,
    )
    _cache[session_id] = session
    _persist(session)
    return session


def get_session(session_id: str) -> Optional[ConversationSession]:
    if session_id in _cache:
        return _cache[session_id]
    # Try loading from DB
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None
    session = _row_to_session(row)
    _cache[session_id] = session
    return session


def append_message(session_id: str, message: ChatMessage) -> None:
    session = get_session(session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")
    session.messages.append(message)
    session.last_active = datetime.utcnow()
    _cache[session_id] = session
    _persist(session)


def list_sessions_for_user(user_id: str) -> list[ConversationSession]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY last_active DESC",
            (user_id,)
        ).fetchall()
    return [_row_to_session(r) for r in rows]


def _persist(session: ConversationSession) -> None:
    messages_json = json.dumps(
        [m.model_dump(mode="json") for m in session.messages]
    )
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO sessions
                (session_id, user_id, entity_context, preferred_provider,
                 messages_json, metadata_json, created_at, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                messages_json    = excluded.messages_json,
                last_active      = excluded.last_active,
                preferred_provider = excluded.preferred_provider
        """, (
            session.session_id,
            session.user_id,
            session.entity_context,
            session.preferred_provider.value,
            messages_json,
            json.dumps(session.metadata),
            session.created_at.isoformat(),
            session.last_active.isoformat(),
        ))
        conn.commit()


def _row_to_session(row: sqlite3.Row) -> ConversationSession:
    raw_messages = json.loads(row["messages_json"])
    messages = [ChatMessage(**m) for m in raw_messages]
    return ConversationSession(
        session_id=row["session_id"],
        user_id=row["user_id"],
        entity_context=row["entity_context"],
        preferred_provider=AIProvider(row["preferred_provider"]),
        messages=messages,
        metadata=json.loads(row["metadata_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        last_active=datetime.fromisoformat(row["last_active"]),
    )
