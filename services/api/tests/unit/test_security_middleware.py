"""Focused regression tests for the request body-size limit middleware.

These tests are fully hermetic: isolated local ASGI / FastAPI applications
only — no Supabase, no Redis, no database, no external services.

HTTP-level tests (TestClient) cover the declared ``Content-Length`` path.
Raw-ASGI tests drive the middleware directly with explicitly controlled
``http.request`` chunk boundaries, which is the only way to exercise the
missing / understated ``Content-Length`` scenarios deterministically.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.security import BodySizeLimitMiddleware

LIMIT = 64  # deliberately tiny limit so oversized bodies stay tiny
OVER_LIMIT = b"x" * (LIMIT + 1)
REJECTION_PAYLOAD = {"detail": "Request body too large"}


# ---------------------------------------------------------------------------
# Raw-ASGI harness
# ---------------------------------------------------------------------------


def http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    """A minimal ASGI http scope."""
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/size",
        "raw_path": b"/size",
        "query_string": b"",
        "root_path": "",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "headers": headers or [],
    }


def request_msg(body: bytes, *, more: bool = False) -> dict:
    return {"type": "http.request", "body": body, "more_body": more}


class RecorderApp:
    """Downstream ASGI app that records invocations and consumed bodies."""

    def __init__(self) -> None:
        self.calls = 0
        self.bodies: list[bytes] = []
        self.scopes: list[dict] = []

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        self.scopes.append(scope)
        body = b""
        while True:
            message = await receive()
            if message.get("type") == "http.request":
                body += message.get("body") or b""
                if not message.get("more_body", False):
                    break
            else:
                break
        self.calls += 1
        self.bodies.append(body)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def run_asgi(
    app,
    scope: dict,
    request_messages: list[dict],
    *,
    exhaust_action: str = "disconnect",
) -> tuple[list[dict], int, list[dict]]:
    """Drive an ASGI app with an explicit request-message queue.

    Returns ``(sent_messages, over_consumed_count, remaining_queue)``.
    ``exhaust_action="raise"`` turns any read past the provided messages into
    an immediate AssertionError, proving rejection did not wait for more data.
    """
    sent: list[dict] = []
    queue = list(request_messages)
    over_consumed = 0

    async def receive() -> dict:
        nonlocal over_consumed
        if queue:
            return queue.pop(0)
        over_consumed += 1
        if exhaust_action == "raise":
            raise AssertionError(
                "middleware consumed more messages than were provided"
            )
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent, over_consumed, queue


def assert_rejected_413(sent: list[dict]) -> None:
    """413 with a valid JSON ``{"detail": ...}`` body."""
    assert sent, "middleware must produce a response"
    start = sent[0]
    assert start["type"] == "http.response.start"
    assert start["status"] == 413
    headers = {name.lower(): value for name, value in start.get("headers", [])}
    assert headers.get(b"content-type", b"").startswith(b"application/json")
    body_message = sent[1]
    assert body_message["type"] == "http.response.body"
    assert json.loads(body_message["body"]) == REJECTION_PAYLOAD


def assert_accepted_200(sent: list[dict]) -> None:
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 200


def build_middleware(recorder: RecorderApp, limit: int = LIMIT):
    return BodySizeLimitMiddleware(recorder, max_body_bytes=limit)


def await_run(app, scope, messages, *, exhaust_action: str = "disconnect"):
    """Run the async harness from a sync test via anyio."""
    import anyio

    return anyio.run(
        lambda: run_asgi(app, scope, messages, exhaust_action=exhaust_action)
    )


# ---------------------------------------------------------------------------
# 1. Oversized declared Content-Length
# ---------------------------------------------------------------------------


class TestDeclaredContentLength:
    def test_oversized_declared_length_rejected_with_valid_json(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope([(b"content-length", str(LIMIT + 1).encode())])
        sent, over_consumed, remaining = await_run(
            mw, scope, [{"type": "http.request", "body": b"", "more_body": False}]
        )
        assert_rejected_413(sent)
        assert recorder.calls == 0
        assert over_consumed == 0
        assert len(remaining) == 1  # body message was never read

    def test_oversized_via_http_client_no_typeerror(self) -> None:
        app, calls = build_fastapi_app(LIMIT)
        with TestClient(app) as client:
            response = client.post("/size", content=OVER_LIMIT)
        assert response.status_code == 413
        # A TypeError from JSONResponse(detail=...) would surface here as a
        # 500; instead the response must be well-formed JSON.
        assert response.json() == REJECTION_PAYLOAD
        assert calls["size"] == 0

    def test_declared_length_within_limit_passes(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope([(b"content-length", str(LIMIT).encode())])
        sent, _, _ = await_run(
            mw,
            scope,
            [{"type": "http.request", "body": b"y" * LIMIT, "more_body": False}],
        )
        assert_accepted_200(sent)
        assert recorder.calls == 1
        assert recorder.bodies == [b"y" * LIMIT]


# ---------------------------------------------------------------------------
# 2-4. Streaming enforcement (Content-Length absent or understated)
# ---------------------------------------------------------------------------


class TestStreamedBodyEnforcement:
    def test_missing_content_length_single_oversized_chunk(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope()  # no content-length header at all
        sent, over_consumed, _ = await_run(
            mw,
            scope,
            [{"type": "http.request", "body": OVER_LIMIT, "more_body": False}],
        )
        assert_rejected_413(sent)
        assert recorder.calls == 0
        assert over_consumed == 0

    def test_missing_content_length_multiple_chunks_cumulative(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope()
        messages = [
            {"type": "http.request", "body": b"a" * 30, "more_body": True},
            {"type": "http.request", "body": b"b" * 30, "more_body": True},
            # 60 bytes so far (accepted); this chunk crosses the cap.
            {"type": "http.request", "body": b"c" * 10, "more_body": False},
        ]
        sent, over_consumed, remaining = await_run(mw, scope, messages)
        assert_rejected_413(sent)
        assert recorder.calls == 0
        assert over_consumed == 0
        assert remaining == []  # the crossing chunk itself was the last one

    def test_understated_content_length_cannot_bypass(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        # Declared 10 bytes, but the client actually streams 80.
        scope = http_scope([(b"content-length", b"10")])
        messages = [
            {"type": "http.request", "body": b"1" * 50, "more_body": True},
            {"type": "http.request", "body": b"2" * 30, "more_body": False},
        ]
        sent, _, _ = await_run(mw, scope, messages)
        assert_rejected_413(sent)
        assert recorder.calls == 0

    def test_rejection_is_immediate_without_consuming_later_data(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope()
        huge_later_chunk = {
            "type": "http.request",
            "body": b"z" * 10_000,
            "more_body": True,
        }
        messages = [
            {"type": "http.request", "body": b"a" * 40, "more_body": True},
            {"type": "http.request", "body": b"b" * 30, "more_body": True},  # 70 > 64
            huge_later_chunk,
        ]
        sent, over_consumed, remaining = await_run(
            mw, scope, messages, exhaust_action="raise"
        )
        assert_rejected_413(sent)
        assert recorder.calls == 0
        assert over_consumed == 0
        assert remaining == [huge_later_chunk]  # never pulled from the queue


# ---------------------------------------------------------------------------
# 5-8. Accepted bodies
# ---------------------------------------------------------------------------


class TestAcceptedBodies:
    def test_empty_body_passes(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope()
        sent, _, _ = await_run(
            mw, scope, [{"type": "http.request", "body": b"", "more_body": False}]
        )
        assert_accepted_200(sent)
        assert recorder.bodies == [b""]

    def test_empty_body_via_http_client_passes(self) -> None:
        app, calls = build_fastapi_app(LIMIT)
        with TestClient(app) as client:
            response = client.post("/size", content=b"")
        assert response.status_code == 200
        assert response.json() == {"received": 0, "body": ""}
        assert calls["size"] == 1

    def test_body_below_limit_passes(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope()
        sent, _, _ = await_run(
            mw, scope, [{"type": "http.request", "body": b"y" * 10, "more_body": False}]
        )
        assert_accepted_200(sent)
        assert recorder.bodies == [b"y" * 10]

    def test_body_exactly_at_limit_passes(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope()  # no declared length; exactly LIMIT bytes streamed
        sent, _, _ = await_run(
            mw,
            scope,
            [{"type": "http.request", "body": b"y" * LIMIT, "more_body": False}],
        )
        assert_accepted_200(sent)
        assert recorder.bodies == [b"y" * LIMIT]

    def test_exactly_at_limit_via_http_client_passes(self) -> None:
        app, calls = build_fastapi_app(LIMIT)
        with TestClient(app) as client:
            response = client.post("/size", content=b"x" * LIMIT)
        assert response.status_code == 200
        assert response.json() == {"received": LIMIT, "body": "x" * LIMIT}
        assert calls["size"] == 1

    def test_accepted_multi_chunk_json_reaches_endpoint_intact(self) -> None:
        """A JSON payload split across ASGI chunks is reconstructed intact.

        Uses the raw-ASGI harness so the chunk boundaries are fully
        controlled (no ``Content-Length`` header is declared).
        """
        app, _calls = build_fastapi_app(LIMIT)
        payload = b'{"hello": "world"}'
        chunk_size = 3  # forces 6 chunks for the 18-byte payload
        chunks = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)]
        assert len(chunks) > 2
        messages = [
            {"type": "http.request", "body": chunk, "more_body": True}
            for chunk in chunks[:-1]
        ] + [{"type": "http.request", "body": chunks[-1], "more_body": False}]
        scope = http_scope([(b"content-type", b"application/json")])

        sent, _, _ = await_run(app, scope, messages)
        assert_accepted_200(sent)
        assert json.loads(sent[1]["body"]) == {
            "received": len(payload),
            "body": payload.decode(),
        }

    def test_accepted_multi_chunk_body_replayed_to_downstream(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope()
        messages = [
            {"type": "http.request", "body": b"part1-", "more_body": True},
            {"type": "http.request", "body": b"part2-", "more_body": True},
            {"type": "http.request", "body": b"part3", "more_body": False},
        ]
        sent, _, _ = await_run(mw, scope, messages)
        assert_accepted_200(sent)
        assert recorder.bodies == [b"part1-part2-part3"]


# ---------------------------------------------------------------------------
# 9. Rejected oversized requests never reach the endpoint
# ---------------------------------------------------------------------------


class TestEndpointNotInvoked:
    def test_streamed_oversized_body_never_invokes_endpoint(self) -> None:
        app, calls = build_fastapi_app(LIMIT)
        scope = http_scope()
        messages = [{"type": "http.request", "body": b"q" * 100, "more_body": False}]
        sent, _, _ = await_run(app, scope, messages)
        assert_rejected_413(sent)
        assert calls["size"] == 0

    def test_declared_oversized_body_never_invokes_endpoint(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope([(b"content-length", str(10**9).encode())])
        sent, _, _ = await_run(
            mw, scope, [{"type": "http.request", "body": b"", "more_body": False}]
        )
        assert_rejected_413(sent)
        assert recorder.calls == 0


# ---------------------------------------------------------------------------
# 11. Disconnect handling
# ---------------------------------------------------------------------------


class TestDisconnectHandling:
    def test_disconnect_before_body_aborts_silently(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope()
        sent, _, _ = await_run(mw, scope, [{"type": "http.disconnect"}])
        assert sent == []  # nothing useful to respond to a gone client
        assert recorder.calls == 0

    def test_disconnect_mid_body_aborts_without_downstream(self) -> None:
        recorder = RecorderApp()
        mw = build_middleware(recorder)
        scope = http_scope()
        messages = [
            {"type": "http.request", "body": b"small-start", "more_body": True},
            {"type": "http.disconnect"},
        ]
        sent, _, _ = await_run(mw, scope, messages)
        assert sent == []
        assert recorder.calls == 0


# ---------------------------------------------------------------------------
# 12. Non-HTTP scopes pass through unchanged
# ---------------------------------------------------------------------------


class TestNonHttpScopes:
    def test_lifespan_scope_passes_through(self) -> None:
        seen_scopes: list[dict] = []

        async def lifespan_app(scope, receive, send) -> None:  # noqa: ANN001
            seen_scopes.append(scope)
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})

        mw = build_middleware(lifespan_app)
        scope = {"type": "lifespan"}
        sent, _, _ = await_run(mw, scope, [{"type": "lifespan.startup"}])
        assert seen_scopes == [scope]
        assert sent == [{"type": "lifespan.startup.complete"}]

    def test_websocket_scope_passes_through(self) -> None:
        async def ws_app(scope, receive, send) -> None:  # noqa: ANN001
            await send({"type": "websocket.accept"})

        mw = build_middleware(ws_app)
        scope = {"type": "websocket", "path": "/ws", "headers": []}
        sent, _, _ = await_run(mw, scope, [{"type": "websocket.connect"}])
        assert sent == [{"type": "websocket.accept"}]


# ---------------------------------------------------------------------------
# HTTP-client level checks (TestClient, isolated FastAPI app)
# ---------------------------------------------------------------------------


def build_fastapi_app(limit: int) -> tuple[FastAPI, dict]:
    """Isolated FastAPI app with the middleware installed and call counters."""
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=limit)
    calls = {"size": 0}

    @app.post("/size")
    async def size(request: Request) -> dict:
        calls["size"] += 1
        raw = await request.body()
        return {"received": len(raw), "body": raw.decode("utf-8", errors="replace")}

    @app.get("/size")
    async def size_get() -> dict:
        calls["size"] += 1
        return {"received": 0}

    return app, calls


def test_get_without_body_passes() -> None:
    app, calls = build_fastapi_app(LIMIT)
    with TestClient(app) as client:
        response = client.get("/size")
    assert response.status_code == 200
    assert response.json() == {"received": 0}
    assert calls["size"] == 1


def test_oversized_post_via_http_client_rejected_before_endpoint() -> None:
    app, calls = build_fastapi_app(LIMIT)
    with TestClient(app) as client:
        response = client.post("/size", content=b"q" * 200)
    assert response.status_code == 413
    assert response.json() == REJECTION_PAYLOAD
    assert calls["size"] == 0



@pytest.mark.parametrize("headers", [[], [(b"content-length", b"1")]])
def test_accepted_scope_and_headers_are_unchanged(headers) -> None:
    recorder = RecorderApp()
    scope = http_scope(headers + [(b"x-custom", b"preserve-me")])
    original_headers = list(scope["headers"])
    sent, _, _ = await_run(
        build_middleware(recorder), scope,
        [request_msg(b"ab", more=True), request_msg(b"cd")],
    )
    assert_accepted_200(sent)
    assert recorder.scopes[0] is scope
    assert scope["headers"] == original_headers
    assert recorder.bodies == [b"abcd"]


def test_real_disconnect_after_replay_is_forwarded() -> None:
    disconnect = {"type": "http.disconnect"}

    async def downstream(scope, receive, send):
        assert await receive() == request_msg(b"ok")
        assert await receive() is disconnect

    _, extra_reads, remaining = await_run(
        build_middleware(downstream), http_scope(),
        [request_msg(b"ok"), disconnect], exhaust_action="raise",
    )
    assert extra_reads == 0
    assert remaining == []


def test_empty_intermediate_chunks_and_omitted_body_pass() -> None:
    recorder = RecorderApp()
    sent, _, _ = await_run(
        build_middleware(recorder), http_scope(),
        [{"type": "http.request", "more_body": True}] * 1000
        + [request_msg(b"x" * LIMIT)],
    )
    assert_accepted_200(sent)
    assert recorder.bodies == [b"x" * LIMIT]


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
@pytest.mark.asyncio
async def test_non_http_passes_original_callables(scope_type) -> None:
    scope = {"type": scope_type}

    async def receive():
        raise AssertionError("middleware must not receive on non-HTTP scopes")

    async def send(message):
        raise AssertionError("middleware must not send on non-HTTP scopes")

    async def downstream(actual_scope, actual_receive, actual_send):
        assert actual_scope is scope
        assert actual_receive is receive
        assert actual_send is send

    await build_middleware(downstream)(scope, receive, send)



