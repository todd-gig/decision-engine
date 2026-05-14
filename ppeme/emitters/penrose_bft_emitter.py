"""penrose_bft_emitter — PPEME→Penrose Scoreboard BFT state emitter.

WHAT: Class `PenroseBFTEmitter` posts canonical-9 BFT state observations
from PPEME's Master Calculator pipeline to decision-engine's
`POST /v1/penrose/network-value/record` inbox. This is the missing wire
that lights up Penrose Scoreboard metric #6 (super_additive_network_value).

WHY: Per `penrose_falsification_doctrine.md` §Scoreboard item 6, the
network-value claim cannot be tested without participant-level state
observations across time. The decision-engine inbox has been live since
penrose-v0.6 (stub-with-formula); until something emits, the metric stays
stubbed. PPEME is the canonical owner of BFT state (Framework 5.19), so
PPEME is the canonical emitter.

WHERE: Called from `ppeme/master_calculator.py` at the point where a
participant's state vector is finalized for a given (org, timestamp).
The emitter writes to the scoreboard inbox; it does NOT persist locally
(PPEME persists its own state in its own store).

WHEN: Fired fire-and-forget on every BFT state finalization. The
scoreboard endpoint accepts duplicates gracefully so over-emission is
safe; under-emission silently degrades metric #6 quality.

HOW: Three-tier defense for "always-online":
  1. Validate the state vector LOCALLY before HTTP — never ship a
     payload that will return 422 (CRIT-010 enforcement).
  2. HTTP errors trigger retry-with-backoff up to 3 attempts; final
     failure logs and emits a local audit metric, never raises.
  3. Lazy-import `requests` so test surfaces and environments without
     the dep stay green.

CONTEXT: Closes "Doctrine-claim ≠ committed code" on metric #6. After
this lands, the doctrine claim "PPEME emits BFT state to the scoreboard"
becomes verifiable by inspecting the network_value_observations table.

penrose_signal: weakens
penrose_dimension: network_value
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)


# Canonical 9-variable BFT state vector — CRIT-010 enforced.
# Mirrors engine.penrose.network_value_emitter.NETWORK_VALUE_STATE_DIMENSIONS
# (single source of truth lives in the inbox; we duplicate the tuple here
# so the emitter can validate WITHOUT importing the receiver, which would
# couple PPEME to decision-engine internals).
BFT_CANONICAL_KEYS: tuple[str, ...] = (
    "trust",
    "attention",
    "clarity",
    "desire",
    "urgency",
    "value",
    "friction",
    "social_proof",
    "context_fit",
)

_DEFAULT_ATTEMPTS = 3
_DEFAULT_BACKOFF_SECONDS = 0.25  # exponential: 0.25, 0.5, 1.0


EmitStatus = Literal["emitted", "dry_run", "disabled", "failed"]


@dataclass
class EmitResult:
    """Result of a single `emit()` call.

    `status` semantics:
      - "emitted":  HTTP 2xx from scoreboard
      - "dry_run":  URL unset OR PENROSE_EMIT_DRY_RUN=1 — payload was valid
                    but no HTTP call was made (logged only)
      - "disabled": Emitter constructed with no URL AND no fallback
                    (functionally same as dry_run; distinguished for ops)
      - "failed":   All retry attempts exhausted; PPEME continued.
    """
    status: EmitStatus
    scoreboard_response: Optional[dict] = None
    attempts: int = 0
    error: Optional[str] = None
    payload: Optional[dict] = field(default=None, repr=False)


class _ValidationError(ValueError):
    """Internal: state vector failed local CRIT-010 validation."""


class PenroseBFTEmitter:
    """Fire-and-forget emitter from PPEME to the Penrose Scoreboard inbox.

    Usage:
        emitter = PenroseBFTEmitter(scoreboard_url="https://decision-engine-...")
        result = emitter.emit(
            participant_id="user-123",
            state_vector={"trust": 0.6, "attention": 0.4, ...},  # all 9 vars
        )

    Hard rules (enforced):
      - Validate state_vector locally BEFORE HTTP (no 422-bound payloads).
      - Never raise on HTTP failure (always-online priority).
      - Never block caller — wrap emit() in a thread pool at call-sites.
      - Lazy-import requests.
    """

    def __init__(
        self,
        scoreboard_url: Optional[str] = None,
        timeout_seconds: int = 5,
        auth_token_env: str = "PENROSE_SCOREBOARD_TOKEN",
        max_attempts: int = _DEFAULT_ATTEMPTS,
        backoff_seconds: float = _DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        # Strip trailing slash for clean URL concat.
        self._scoreboard_url = (scoreboard_url or "").rstrip("/") or None
        self._timeout = int(timeout_seconds)
        self._auth_token_env = auth_token_env
        self._max_attempts = max(1, int(max_attempts))
        self._backoff = max(0.0, float(backoff_seconds))

    # ── public API ──────────────────────────────────────────────────────────

    def emit(
        self,
        participant_id: str,
        state_vector: dict,
        timestamp: Optional[str] = None,
        source: str = "ppeme",
    ) -> EmitResult:
        """Emit one (participant_id, state_vector, timestamp) observation.

        Returns an EmitResult. Never raises (except on programmer-error
        in participant_id / state_vector validation — those surface so
        the Master Calculator catches its own bugs).
        """
        # Local validation — refuse to ship payloads that would 422.
        try:
            self._validate_participant(participant_id)
            self._validate_state_vector(state_vector)
        except _ValidationError as exc:
            # Programmer error in caller — re-raise as ValueError so
            # PPEME's own tests catch this in dev/CI. We do NOT swallow
            # this because shipping bad payloads silently is worse than
            # crashing the offending code path during development.
            raise ValueError(str(exc)) from exc

        payload = {
            "participant_id": participant_id,
            "state_vector": state_vector,
            "timestamp": timestamp or datetime.now(tz=timezone.utc).isoformat(),
            "source": source,
        }

        # Dry-run paths (no HTTP).
        if os.environ.get("PENROSE_EMIT_DRY_RUN") == "1":
            logger.info(
                "penrose_bft_emitter: DRY_RUN — would emit participant=%s",
                participant_id,
            )
            return EmitResult(status="dry_run", payload=payload, attempts=0)

        if not self._scoreboard_url:
            logger.info(
                "penrose_bft_emitter: disabled (no scoreboard URL) — "
                "skipping participant=%s",
                participant_id,
            )
            return EmitResult(status="disabled", payload=payload, attempts=0)

        return self._post_with_retry(payload)

    # ── internals ───────────────────────────────────────────────────────────

    @staticmethod
    def _validate_participant(participant_id: Any) -> None:
        if not isinstance(participant_id, str) or not participant_id.strip():
            raise _ValidationError(
                "participant_id must be a non-empty string"
            )

    @staticmethod
    def _validate_state_vector(state_vector: Any) -> None:
        if not isinstance(state_vector, dict):
            raise _ValidationError(
                "state_vector must be a dict mapping each of the canonical "
                f"9 BFT variables to a value in [0, 1]; got "
                f"{type(state_vector).__name__}"
            )
        keys = set(state_vector.keys())
        canonical = set(BFT_CANONICAL_KEYS)
        if keys != canonical:
            missing = sorted(canonical - keys)
            extra = sorted(keys - canonical)
            raise _ValidationError(
                "state_vector must contain EXACTLY the canonical 9 BFT "
                f"variables (CRIT-010, §5.19); missing={missing}, "
                f"extra={extra}"
            )
        for k, v in state_vector.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise _ValidationError(
                    f"state_vector[{k!r}] must be numeric (int/float); "
                    f"got {type(v).__name__}"
                )
            if not (0.0 <= float(v) <= 1.0):
                raise _ValidationError(
                    f"state_vector[{k!r}] = {v!r} is out of range [0, 1] "
                    f"(CRIT-010 — scoreboard inbox rejects non-normalized "
                    f"values with HTTP 422)"
                )

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        tok = os.environ.get(self._auth_token_env)
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def _post_with_retry(self, payload: dict) -> EmitResult:
        """POST with exponential backoff. Never raises."""
        # Lazy-import so test surfaces / minimal envs don't need requests.
        try:
            import requests  # type: ignore
        except ImportError:
            logger.warning(
                "penrose_bft_emitter: `requests` not installed — "
                "treating as failed emission (install requests in prod)"
            )
            self._audit_failure(payload, "requests_not_installed")
            return EmitResult(
                status="failed",
                attempts=0,
                error="requests_not_installed",
                payload=payload,
            )

        url = self._scoreboard_url + "/v1/penrose/network-value/record"
        last_error: Optional[str] = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                resp = requests.post(
                    url,
                    data=json.dumps(payload),
                    headers=self._headers(),
                    timeout=self._timeout,
                )
                if 200 <= resp.status_code < 300:
                    try:
                        body = resp.json()
                    except (ValueError, json.JSONDecodeError):
                        body = None
                    return EmitResult(
                        status="emitted",
                        scoreboard_response=body,
                        attempts=attempt,
                        payload=payload,
                    )
                # 4xx other than transient lockup is unlikely-but-recoverable
                # in practice (scoreboard could be mid-deploy returning 503).
                # Retry the same payload — over-emission is safe.
                last_error = f"http_{resp.status_code}"
                logger.info(
                    "penrose_bft_emitter: HTTP %s on attempt %d/%d "
                    "(participant=%s)",
                    resp.status_code, attempt, self._max_attempts,
                    payload.get("participant_id"),
                )
            except Exception as exc:  # noqa: BLE001
                # `requests.exceptions.ConnectionError`, Timeout, etc.
                last_error = type(exc).__name__
                logger.info(
                    "penrose_bft_emitter: %s on attempt %d/%d "
                    "(participant=%s): %s",
                    last_error, attempt, self._max_attempts,
                    payload.get("participant_id"), exc,
                )

            if attempt < self._max_attempts:
                sleep_for = self._backoff * (2 ** (attempt - 1))
                time.sleep(sleep_for)

        # All attempts exhausted — log + audit + return failed (no raise).
        self._audit_failure(payload, last_error or "unknown")
        return EmitResult(
            status="failed",
            attempts=self._max_attempts,
            error=last_error,
            payload=payload,
        )

    @staticmethod
    def _audit_failure(payload: dict, reason: str) -> None:
        """Emit metric `penrose_emit_failed` to local audit log.

        Today this is a structured log line; future versions could write to
        an SQLite audit table or fire a Pub/Sub event. The format is stable
        so a log-based metric can be defined against it.
        """
        logger.warning(
            "penrose_emit_failed reason=%s participant=%s timestamp=%s",
            reason,
            payload.get("participant_id"),
            payload.get("timestamp"),
        )
