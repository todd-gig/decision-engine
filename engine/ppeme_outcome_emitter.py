"""PPEME outcome emitter — fire observed outcomes from decision-engine.

When an outcome becomes observable for a prior decision (closed-won
opportunity, completed initiative, measured revenue window, etc.), this
module emits the outcome to PPEME's /v1/outcomes/record endpoint.

That endpoint feeds:
  - PPEME's outcomes table (raw ingest)
  - jobs.recompute_calibration → estimator_calibration table
  - MAJ-018 enforcement (forecast authority gating)

Design mirrors hme_event_emitter (same repo): fire-and-forget HTTP POST,
stdlib-only (urllib.request), identity token via metadata server,
silent failure — pipeline / caller is NEVER blocked by PPEME availability.

Configuration:
  PPEME_URL                     base URL of PPEME Cloud Run service
                                (falls back to GATEWAY_URL+/v1/ppeme then to disabled)
  DECISION_PPEME_EMIT_DISABLED  kill-switch
  DECISION_PPEME_DISABLE_OIDC   skip identity token (local dev / tests)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


_SUBJECT_KINDS = frozenset({"user", "org", "platform_aggregate"})


def _identity_token(audience: str) -> Optional[str]:
    """Fetch GCP identity token via metadata server (Cloud Run pattern)."""
    if os.environ.get("DECISION_PPEME_DISABLE_OIDC") == "1":
        return None
    try:
        meta_url = (
            "http://metadata.google.internal/computeMetadata/v1/instance/"
            f"service-accounts/default/identity?audience={audience}"
        )
        req = urllib.request.Request(meta_url, headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status != 200:
                return None
            return resp.read().decode("utf-8").strip()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    except Exception:  # noqa: BLE001
        return None


def _ppeme_base_url() -> Optional[str]:
    """Resolve PPEME base URL from env, preferring direct PPEME_URL."""
    if os.environ.get("DECISION_PPEME_EMIT_DISABLED") == "1":
        return None
    direct = os.environ.get("PPEME_URL")
    if direct:
        return direct.rstrip("/")
    gateway = os.environ.get("GATEWAY_URL")
    if gateway:
        # Default convention: gateway proxies /v1/ppeme/* to PPEME
        return gateway.rstrip("/") + "/v1/ppeme"
    return None


def emit_observed_outcome(
    *,
    decision_id: Optional[str],
    decision_certificate_id: Optional[str] = None,
    subject_kind: str,
    subject_id: Optional[str] = None,
    outcome_metric: str,
    outcome_value: float,
    outcome_unit: str,
    observed_at: Optional[str] = None,
    observation_window_start: Optional[str] = None,
    observation_window_end: Optional[str] = None,
    why: Optional[str] = None,
    predicted_p50: Optional[float] = None,
    estimator_version: Optional[str] = None,
    decision_class: Optional[str] = None,
    extra_metadata: Optional[dict[str, Any]] = None,
) -> bool:
    """Emit an observed outcome to PPEME /v1/outcomes/record.

    Returns True on HTTP 2xx; False on any failure.

    The (predicted_p50, estimator_version, decision_class) trio populates
    metadata_payload so recompute_calibration can group + compute variance.
    Outcomes without that trio still ingest, but variance computation
    skips them (per the orphan logic in jobs.recompute_calibration).
    """
    if subject_kind not in _SUBJECT_KINDS:
        logger.warning(
            "ppeme_outcome_emitter: invalid subject_kind %r; skipping",
            subject_kind,
        )
        return False

    base = _ppeme_base_url()
    if not base:
        return False  # disabled in local dev / tests

    metadata = dict(extra_metadata or {})
    if predicted_p50 is not None:
        metadata["predicted_p50"] = predicted_p50
    if estimator_version is not None:
        metadata["estimator_version"] = estimator_version
    if decision_class is not None:
        metadata["decision_class"] = decision_class

    payload: dict[str, Any] = {
        "subject_kind": subject_kind,
        "outcome_metric": outcome_metric,
        "outcome_value": outcome_value,
        "outcome_unit": outcome_unit,
        "observed_at": observed_at or datetime.now(tz=timezone.utc).isoformat(),
        "source_engine": "decision-engine",
    }
    if decision_id is not None:
        payload["decision_id"] = decision_id
    if decision_certificate_id is not None:
        payload["decision_certificate_id"] = decision_certificate_id
    if subject_id is not None:
        payload["subject_id"] = subject_id
    if observation_window_start is not None:
        payload["observation_window_start"] = observation_window_start
    if observation_window_end is not None:
        payload["observation_window_end"] = observation_window_end
    if why is not None:
        payload["why"] = why
    if metadata:
        payload["metadata_payload"] = metadata

    url = base + "/v1/outcomes/record"
    headers = {"Content-Type": "application/json"}
    token = _identity_token(base)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        logger.info(
            "ppeme_outcome_emitter: HTTP %s emitting outcome for decision=%s",
            exc.code, decision_id,
        )
        return False
    except urllib.error.URLError as exc:
        logger.info(
            "ppeme_outcome_emitter: network error for decision=%s: %s",
            decision_id, exc.reason,
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.info("ppeme_outcome_emitter: unexpected error: %s", exc)
        return False
