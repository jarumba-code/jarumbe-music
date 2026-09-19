"""Request-ID handling tests (Phase 13 hardening).

``X-Request-ID`` is an untrusted client header.  The middleware only accepts
values matching ``[A-Za-z0-9._:-]{1,64}``; anything else (CR/LF, control
characters, non-ASCII, over-length values) is replaced by a server-generated
UUID4 hex so it can never be echoed into a response header or a log line.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.request_id import sanitize_request_id


_SAFE_ID = "frontend-abc123"


# ---------------------------------------------------------------------------
# Unit tests for sanitize_request_id
# ---------------------------------------------------------------------------


class TestSanitizeRequestId:
    def test_valid_id_is_preserved(self):
        assert sanitize_request_id(_SAFE_ID) == _SAFE_ID

    def test_all_allowed_characters(self):
        candidate = "AZaz09.-:_"
        assert sanitize_request_id(candidate) == candidate

    def test_maximum_length_is_accepted(self):
        candidate = "a" * 64
        assert sanitize_request_id(candidate) == candidate

    @pytest.mark.parametrize(
        "unsafe",
        [
            "a" * 65,               # one character too long
            "with\rCR",             # carriage return
            "with\nLF",             # line feed
            "with\ttab",            # tab
            "with\x00nul",          # NUL
            "with\x1besc",          # escape / control character
            "with space",           # space inside
            "ünïcode",              # non-ASCII
            "id+plus",              # '+' is not in the allow-list
            "id/slash",             # '/' is not in the allow-list
        ],
    )
    def test_unsafe_values_are_replaced(self, unsafe):
        generated = sanitize_request_id(unsafe)
        assert generated != unsafe
        assert _SAFE_ID != generated  # (noise to keep linters honest)
        assert re.fullmatch(r"[0-9a-f]{32}", generated)

    def test_surrounding_whitespace_is_stripped_not_rejected(self):
        assert sanitize_request_id(f"  {_SAFE_ID}  ") == _SAFE_ID

    def test_empty_and_none_generate_an_id(self):
        for raw in ("", None, "   "):
            assert re.fullmatch(r"[0-9a-f]{32}", sanitize_request_id(raw))

    def test_generated_ids_are_unique(self):
        first = sanitize_request_id(None)
        second = sanitize_request_id(None)
        assert first != second


# ---------------------------------------------------------------------------
# Middleware integration
# ---------------------------------------------------------------------------


@pytest.fixture()
def request_id_client():
    with TestClient(app) as client:
        yield client


class TestRequestIdMiddleware:
    def test_response_carries_the_request_id(self, request_id_client):
        response = request_id_client.get("/health", headers={"X-Request-ID": _SAFE_ID})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == _SAFE_ID

    def test_unsafe_id_is_replaced_with_server_generated_value(
        self, request_id_client
    ):
        malicious = f"{_SAFE_ID}\r\nX-Evil: injected"
        response = request_id_client.get("/health", headers={"X-Request-ID": malicious})
        assert response.status_code == 200
        returned = response.headers["X-Request-ID"]
        assert returned != malicious
        assert re.fullmatch(r"[0-9a-f]{32}", returned)
        # No injected header may appear in the response.
        assert "x-evil" not in {k.lower() for k in response.headers}

    def test_overlong_id_is_replaced(self, request_id_client):
        response = request_id_client.get(
            "/health", headers={"X-Request-ID": "x" * 500}
        )
        assert response.status_code == 200
        assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])

    def test_error_responses_carry_the_request_id(self, request_id_client):
        # 401 from /api/v1/auth/me — the header must survive error paths too.
        response = request_id_client.get(
            "/api/v1/auth/me", headers={"X-Request-ID": _SAFE_ID}
        )
        assert response.status_code == 401
        assert response.headers["X-Request-ID"] == _SAFE_ID

    def test_distinct_requests_get_distinct_ids(self, request_id_client):
        first = request_id_client.get("/health").headers["X-Request-ID"]
        second = request_id_client.get("/health").headers["X-Request-ID"]
        assert first != second
        assert re.fullmatch(r"[0-9a-f]{32}", first)
        assert re.fullmatch(r"[0-9a-f]{32}", second)
