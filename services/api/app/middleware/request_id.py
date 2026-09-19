"""Request-ID + structured access-log middleware.

Every request gets a unique ID (``X-Request-ID``, propagated from an
upstream-supplied value when present).  The ID is returned in the response
header and included in every access-log line:

    ts level event method path status request_id duration_ms

Tokens, query strings, and bodies are never logged.

Security notes
--------------
``X-Request-ID`` is an untrusted request header, so an inbound value is only
accepted when it matches a strict allow-list of characters and a bounded
length (see :data:`_REQUEST_ID_PATTERN`).  Anything else — CR/LF, other
control characters, an over-long value — is discarded and replaced with a
server-generated ID, which prevents response-header injection and log
injection through this field.
"""

from __future__ import annotations

import logging
import re
import sys
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("jarumba.access")

if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


#: Accepted inbound request IDs: printable, log/header-safe characters only.
_REQUEST_ID_PATTERN = re.compile(r"\A[A-Za-z0-9._:\-]{1,64}\Z")


def sanitize_request_id(raw: str | None) -> str:
    """Return a safe request ID for *raw*, or a freshly generated one.

    Unsafe values (control characters such as CR/LF, tabs, NUL, non-ASCII
    bytes, or anything longer than 64 characters) are never echoed back and
    are never logged: they are replaced with a server-generated UUID4 hex.
    """
    if raw:
        candidate = raw.strip()
        if _REQUEST_ID_PATTERN.match(candidate):
            return candidate
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN201
        request_id = sanitize_request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000.0
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "event=http_request method=%s path=%s status=%s request_id=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            duration_ms,
        )
        return response

