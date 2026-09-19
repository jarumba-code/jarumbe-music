"""API security middleware: response headers + request body-size cap.

Headers (JSON API — browser-only headers like CSP/Frame-ancestors are not
meaningfully applicable to a native mobile client and are omitted):

* ``X-Content-Type-Options: nosniff``
* ``Referrer-Policy: no-referrer``
* ``Cache-Control: no-store`` (JWT-authenticated responses must never be
  cached by any intermediary)

The body-size middleware rejects requests whose declared or streamed body
exceeds ``settings.max_request_body_bytes`` with HTTP 413.  It is a pure
ASGI middleware so it can count the *actual* bytes received — not just the
declared ``Content-Length`` — and abort the moment the cap is crossed.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN201
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response


class BodySizeLimitMiddleware:
    """Reject request bodies larger than ``max_body_bytes`` with HTTP 413.

    Enforcement is based on the bytes actually received, not on the declared
    size alone:

    * A ``Content-Length`` that already exceeds the cap is rejected before
      any body bytes are read.
    * When the header is absent — or understates the real size — the
      incoming ``http.request`` messages are counted incrementally and the
      request is aborted the moment the cumulative size crosses the cap.
      Remaining chunks are never consumed and the downstream endpoint is
      never invoked.
    * An accepted request is replayed downstream as a single buffered body.
      Buffering is strictly bounded by the cap, so memory use can never
      grow unbounded regardless of how the client streams.
    * A client disconnect aborts the request silently; non-HTTP scopes
      (lifespan, websocket) pass through untouched.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only HTTP requests carry a body; everything else passes through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = self._declared_content_length(scope)
        if declared is not None and declared > self._max_body_bytes:
            await self._reject(scope, receive, send)
            return

        buffered = bytearray()

        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                # Never invoke an endpoint with an incomplete request.
                return
            body = message.get("body", b"")
            if len(buffered) + len(body) > self._max_body_bytes:
                await self._reject(scope, receive, send)
                return
            buffered.extend(body)
            if not message.get("more_body", False):
                break

        # Coalesce transport chunks without changing the body or scope/headers.
        full_body = bytes(buffered)
        del buffered
        await self.app(scope, self._replayed_receive(full_body, receive), send)

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _declared_content_length(scope: Scope) -> int | None:
        """Best-effort declared size; ``None`` when absent or malformed."""
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                raw = value.decode("latin-1").strip()
                try:
                    return int(raw)
                except ValueError:
                    return None
        return None

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "Request body too large"},
        )
        await response(scope, receive, send)

    @staticmethod
    def _replayed_receive(body: bytes, original_receive: Receive) -> Receive:
        """Replay once, then preserve real disconnect notifications."""
        sent = False

        async def receive() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await original_receive()

        return receive

