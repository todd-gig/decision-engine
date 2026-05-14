"""Tests for GigatonClient — stdlib-only HTTP client + auth resolution."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from io import BytesIO
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gigaton_client import GigatonClient, GigatonClientError


def _http_response(payload: dict, status: int = 200) -> mock.MagicMock:
    """Build a mock urlopen response with the given JSON payload."""
    m = mock.MagicMock()
    m.__enter__ = mock.MagicMock(return_value=m)
    m.__exit__ = mock.MagicMock(return_value=None)
    m.read.return_value = json.dumps(payload).encode("utf-8")
    m.status = status
    return m


class TestGigatonClient:
    def test_uses_explicit_base_url(self):
        c = GigatonClient(base_url="https://override.example")
        assert c.base_url == "https://override.example"

    def test_strips_trailing_slash(self):
        c = GigatonClient(base_url="https://override.example/")
        assert c.base_url == "https://override.example"

    def test_uses_env_var_when_no_base_url(self, monkeypatch):
        monkeypatch.setenv("GIGATON_ENGINE_URL", "https://env.example")
        c = GigatonClient()
        assert c.base_url == "https://env.example"

    def test_falls_back_to_cloud_run_default(self, monkeypatch):
        monkeypatch.delenv("GIGATON_ENGINE_URL", raising=False)
        c = GigatonClient()
        assert "gigaton-engine" in c.base_url and "run.app" in c.base_url

    def test_health_returns_dict(self):
        c = GigatonClient(base_url="https://test.example")
        with mock.patch("urllib.request.urlopen", return_value=_http_response({"status": "ok"})):
            with mock.patch.object(c, "_resolve_identity_token", return_value=None):
                result = c.health()
        assert result == {"status": "ok"}

    def test_get_pricing_posts_payload(self):
        c = GigatonClient(base_url="https://test.example")
        called = {}

        def fake_urlopen(req, timeout):
            called["url"] = req.full_url
            called["method"] = req.method
            called["body"] = req.data
            return _http_response({"nightly_rate": 180})

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with mock.patch.object(c, "_resolve_identity_token", return_value=None):
                result = c.get_pricing({"property_id": "prop_123"})

        assert result == {"nightly_rate": 180}
        assert called["url"].endswith("/pricing/quote")
        assert called["method"] == "POST"
        assert json.loads(called["body"]) == {"property_id": "prop_123"}

    def test_get_margin_posts_payload(self):
        c = GigatonClient(base_url="https://test.example")
        with mock.patch("urllib.request.urlopen", return_value=_http_response({"recommendation": "hold"})):
            with mock.patch.object(c, "_resolve_identity_token", return_value=None):
                result = c.get_margin({"property_id": "prop_123", "horizon_days": 30})
        assert result == {"recommendation": "hold"}

    def test_http_error_raises_client_error_with_status(self):
        c = GigatonClient(base_url="https://test.example")
        err = urllib.error.HTTPError(
            "https://test.example/health", 503, "Service Unavailable",
            hdrs=None, fp=BytesIO(b'{"error":"down"}')
        )
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with mock.patch.object(c, "_resolve_identity_token", return_value=None):
                with pytest.raises(GigatonClientError) as exc_info:
                    c.health()
        assert exc_info.value.status_code == 503

    def test_network_error_raises_client_error_with_status_0(self):
        c = GigatonClient(base_url="https://test.example")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            with mock.patch.object(c, "_resolve_identity_token", return_value=None):
                with pytest.raises(GigatonClientError) as exc_info:
                    c.health()
        assert exc_info.value.status_code == 0


class TestAuth:
    def test_explicit_token_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("GCP_IDENTITY_TOKEN", "explicit-token-from-env")
        c = GigatonClient(base_url="https://test.example")
        assert c._resolve_identity_token() == "explicit-token-from-env"

    def test_no_token_returns_none_locally(self, monkeypatch):
        # Force all three resolution paths to fail
        monkeypatch.delenv("GCP_IDENTITY_TOKEN", raising=False)
        c = GigatonClient(base_url="https://test.example")

        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("metadata unavailable")):
            # Also mock the google-auth fallback to fail (it would also fail if
            # google-auth is uninstalled, but we mock to be deterministic)
            with mock.patch.dict(sys.modules, {
                "google.auth.transport.requests": None,
                "google.oauth2.id_token": None,
            }):
                token = c._resolve_identity_token()
        assert token is None

    def test_metadata_server_token_returned_when_available(self, monkeypatch):
        monkeypatch.delenv("GCP_IDENTITY_TOKEN", raising=False)
        c = GigatonClient(base_url="https://test.example")

        fake_resp = mock.MagicMock()
        fake_resp.__enter__ = mock.MagicMock(return_value=fake_resp)
        fake_resp.__exit__ = mock.MagicMock(return_value=None)
        fake_resp.read.return_value = b"oidc-token-from-metadata"

        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            token = c._resolve_identity_token()
        assert token == "oidc-token-from-metadata"

    def test_auth_header_set_when_token_resolved(self):
        c = GigatonClient(base_url="https://test.example")
        with mock.patch.object(c, "_resolve_identity_token", return_value="test-token"):
            headers = c._auth_headers()
        assert headers["Authorization"] == "Bearer test-token"

    def test_auth_header_empty_when_no_token(self):
        c = GigatonClient(base_url="https://test.example")
        with mock.patch.object(c, "_resolve_identity_token", return_value=None):
            headers = c._auth_headers()
        assert headers == {}
