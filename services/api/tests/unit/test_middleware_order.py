"""Middleware-stack order regression tests.

``app/main.py`` documents the effective runtime order (outermost first):

    1. RequestIdMiddleware       request ID + structured access log
    2. CORSMiddleware            explicit origin allow-list
    3. SecurityHeadersMiddleware nosniff / no-referrer / no-store
    4. BodySizeLimitMiddleware   413 before any body is parsed
    5. TrustedHostMiddleware     Host allow-list
    6. GZipMiddleware            compression, innermost

Starlette's ``add_middleware`` *prepends* to ``app.user_middleware`` and the
stack is built so that the **last added** middleware is the **outermost**.
This file pins the resulting order so the documented sequence cannot silently
drift.  Note that JWT verification is a FastAPI *dependency*, not middleware:
it runs after the whole middleware stack, inside route dependency resolution
(which is also why rate limiting, a route-level dependency, executes before
token verification).
"""

from __future__ import annotations

from app.main import app

#: Outermost first — exactly the order documented in ``app/main.py``.
EXPECTED_OUTERMOST_FIRST = [
    "RequestIdMiddleware",
    "CORSMiddleware",
    "SecurityHeadersMiddleware",
    "BodySizeLimitMiddleware",
    "TrustedHostMiddleware",
    "GZipMiddleware",
]


def _stack_class_names() -> list[str]:
    """Class names of the registered middleware, outermost first."""
    return [middleware.cls.__name__ for middleware in app.user_middleware]


class TestMiddlewareStackOrder:
    def test_documented_order_is_pinned(self):
        assert _stack_class_names() == EXPECTED_OUTERMOST_FIRST

    def test_request_id_is_outermost(self):
        names = _stack_class_names()
        assert names[0] == "RequestIdMiddleware", (
            "every response (including 413/429 short-circuits) must carry "
            "X-Request-ID and be access-logged"
        )

    def test_body_size_limit_sits_inside_security_headers(self):
        names = _stack_class_names()
        assert names.index("BodySizeLimitMiddleware") > names.index(
            "SecurityHeadersMiddleware"
        ), "413 short-circuits must still receive the security headers"

    def test_gzip_is_innermost(self):
        names = _stack_class_names()
        assert names[-1] == "GZipMiddleware"

    def test_body_size_limit_uses_the_configured_limit(self):
        from app.config import get_settings

        body_middleware = next(
            m
            for m in app.user_middleware
            if m.cls.__name__ == "BodySizeLimitMiddleware"
        )
        assert (
            body_middleware.kwargs["max_body_bytes"]
            == get_settings().max_request_body_bytes
        )
