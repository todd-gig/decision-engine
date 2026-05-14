"""HTTP client for the Gigaton Engine service (Cloud Run).

The decision-engine gate layer calls this to delegate pricing, margin
optimisation, and agent-coordination decisions to gigaton-engine.

# Usage
#
#   from gigaton_client import GigatonClient, GigatonClientError
#
#   client = GigatonClient()               # reads GIGATON_ENGINE_URL env var
#                                          # falls back to the Cloud Run URL
#
#   # Health probe
#   status = client.health()               # {'status': 'ok', ...}
#
#   # Pricing quote (gate layer pattern)
#   try:
#       quote = client.get_pricing({
#           'property_id': 'prop_123',
#           'check_in': '2026-06-01',
#           'check_out': '2026-06-07',
#           'adults': 2,
#       })
#       nightly_rate = quote['nightly_rate']
#   except GigatonClientError as exc:
#       if exc.status_code == 503:
#           # gigaton-engine unavailable — fall back to cached rate sheet
#           nightly_rate = _cached_rate()
#       else:
#           raise
#
#   # Margin optimisation
#   result = client.get_margin({'property_id': 'prop_123', 'horizon_days': 30})
#
#   # Agent coordination
#   agents = client.get_agents({'task': 'clean_turnover', 'property_id': 'prop_123'})
"""

from __future__ import annotations

import json as _json
import os
import urllib.request
import urllib.error
from typing import Optional

# ── Cloud Run default ─────────────────────────────────────────────────────────

_DEFAULT_BASE_URL = "https://gigaton-engine-rjmcrtvuzq-uc.a.run.app"

# ── Error class ───────────────────────────────────────────────────────────────


class GigatonClientError(Exception):
    """Raised when gigaton-engine returns a non-2xx HTTP response.

    Attributes:
        status_code: The HTTP status code returned by the service.
        body: The raw response body as a string.
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"GigatonEngine HTTP {status_code}: {body[:200]}")


# ── Client ────────────────────────────────────────────────────────────────────


class GigatonClient:
    """Stdlib-only HTTP client for the Gigaton Engine service.

    Attaches a GCP identity token when running on Cloud Run (service-to-service
    auth).  Token resolution order:
    1. ``GCP_IDENTITY_TOKEN`` env var (injected by Cloud Run metadata server or
       CI pipeline)
    2. ``google.oauth2.id_token`` library (if installed; lazy import, fails
       silently so local dev works without GCP credentials)
    3. No ``Authorization`` header (unauthenticated — only works if the service
       allows public ingress, which it does not in production)

    Args:
        base_url: Override the gigaton-engine base URL.  Reads
            ``GIGATON_ENGINE_URL`` env var when ``None``; falls back to the
            hardcoded Cloud Run URL.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        resolved = (
            base_url
            or os.environ.get("GIGATON_ENGINE_URL", "")
            or _DEFAULT_BASE_URL
        )
        self.base_url = resolved.rstrip("/")

    # ── Public methods ────────────────────────────────────────────────────────

    def health(self) -> dict:
        """GET /health — liveness probe."""
        return self._get("/health")

    def get_pricing(self, payload: dict) -> dict:
        """POST /pricing/quote — request a pricing quote from gigaton-engine.

        Args:
            payload: Arbitrary dict forwarded as JSON.  Expected keys vary by
                property type; at minimum include ``property_id``.

        Returns:
            Parsed JSON response dict from the engine.

        Raises:
            GigatonClientError: On any non-2xx response.
        """
        return self._post("/pricing/quote", payload)

    def get_margin(self, payload: dict) -> dict:
        """POST /margin/optimize — request margin optimisation.

        Args:
            payload: Optimisation parameters (``property_id``,
                ``horizon_days``, etc.).

        Returns:
            Parsed JSON response dict from the engine.

        Raises:
            GigatonClientError: On any non-2xx response.
        """
        return self._post("/margin/optimize", payload)

    def get_agents(self, payload: dict) -> dict:
        """POST /agents/coordinate — dispatch a multi-agent task.

        Args:
            payload: Task description (``task``, ``property_id``, etc.).

        Returns:
            Parsed JSON response dict from the engine.

        Raises:
            GigatonClientError: On any non-2xx response.
        """
        return self._post("/agents/coordinate", payload)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get(self, path: str) -> dict:
        url = self.base_url + path
        headers = self._auth_headers()
        headers["Accept"] = "application/json"
        req = urllib.request.Request(url, headers=headers, method="GET")
        return self._execute(req)

    def _post(self, path: str, payload: dict) -> dict:
        url = self.base_url + path
        body = _json.dumps(payload).encode("utf-8")
        headers = self._auth_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        return self._execute(req)

    def _execute(self, req: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            return _json.loads(raw)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise GigatonClientError(exc.code, body) from exc
        except urllib.error.URLError as exc:
            # Connection-level failure (DNS, timeout, refused)
            raise GigatonClientError(0, str(exc.reason)) from exc

    def _auth_headers(self) -> dict[str, str]:
        """Build Authorization headers if a GCP identity token is available."""
        token = self._resolve_identity_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def _resolve_identity_token(self) -> Optional[str]:
        """Resolve a GCP identity token — never raises, returns None on failure.

        Token resolution order:
          1. GCP_IDENTITY_TOKEN env var (CI / local override)
          2. Cloud Run metadata server (works for attached SAs without a key
             file — the `id_token.fetch_id_token` library path was tried first
             but returns None for Cloud Run SAs; see hme_deploy_post_mortem_2026_05_13
             for the diagnostic that surfaced this).
          3. google-auth library fetch_id_token (works when a service-account
             key file is configured; useful for local dev)
        """
        token = os.environ.get("GCP_IDENTITY_TOKEN", "")
        if token:
            return token

        # 2. Metadata server (Cloud Run attached SA — the production path)
        try:
            req = urllib.request.Request(
                "http://metadata.google.internal/computeMetadata/v1/instance/"
                f"service-accounts/default/identity?audience={self.base_url}",
                headers={"Metadata-Flavor": "Google"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8")
            if body:
                return body
        except Exception:
            pass

        # 3. google-auth library (lazy, fail silently — local dev path)
        try:
            import google.auth.transport.requests as _gtr  # type: ignore[import]
            import google.oauth2.id_token as _id_token  # type: ignore[import]

            audience = self.base_url
            request = _gtr.Request()
            return _id_token.fetch_id_token(request, audience)
        except Exception:
            return None
