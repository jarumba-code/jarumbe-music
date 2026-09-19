from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.deps import rate_limiter
from app.api.routes.auth import router as auth_router
from app.api.routes.favorites import router as favorites_router
from app.api.routes.music import router as music_router
from app.api.routes.playlist_tracks import router as playlist_tracks_router
from app.api.routes.playlists import router as playlists_router
from app.api.routes.profile import router as profile_router
from app.api.routes.recently_played import router as recently_played_router
from app.config import get_settings
from app.database import get_db
from app.middleware.request_id import RequestIdMiddleware, logger as app_logger
from app.middleware.security import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.services.rate_limit import require_shared_rate_limit_backend

settings = get_settings()

# Explicit environment policy: a deployed environment must never silently fall
# back to per-process rate-limit counters (each replica would enforce its own,
# weaker limits).  Fail fast at import time instead.
require_shared_rate_limit_backend(settings)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    responses={
        401: {"description": "Authentication required or token rejected"},
        403: {"description": "Authenticated user is not allowed to perform this action"},
        404: {"description": "Requested resource was not found"},
        409: {"description": "Request conflicts with existing state"},
        429: {"description": "Rate limit exceeded"},
        502: {"description": "Upstream music provider returned an invalid response"},
        503: {"description": "Required service is temporarily unavailable"},
    },
)

# --- Middleware stack --------------------------------------------------------
# Starlette assembles the stack from ``app.user_middleware`` in reverse, and
# ``add_middleware`` *prepends* to that list — so the LAST call below is the
# OUTERMOST layer.  The effective runtime order (outermost first) is the
# reverse of the call order:
#
#   1. RequestIdMiddleware       request ID + structured access log, outermost
#                                so *every* response (including the 413/400
#                                short-circuits produced below) carries
#                                X-Request-ID and is logged
#   2. CORSMiddleware            explicit origin allow-list, no credentials
#   3. SecurityHeadersMiddleware nosniff / no-referrer / no-store
#   4. BodySizeLimitMiddleware   413 before any body is parsed
#   5. TrustedHostMiddleware     Host allow-list
#   6. GZipMiddleware            large-payload compression, innermost
#
# ``tests/unit/test_middleware_order.py`` pins this order against
# ``app.user_middleware``.
app.add_middleware(GZipMiddleware, minimum_size=1024)
# Trusted hosts â€” "*" is only acceptable in local development.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
# Reject oversized request bodies (413) and add security headers.
app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=settings.max_request_body_bytes)
app.add_middleware(SecurityHeadersMiddleware)
# Explicit, environment-driven CORS.  No wildcard origin is combined with
# credentials; the native mobile client needs no CORS at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=[
        "X-Request-ID",
        "Retry-After",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Scope",
    ],
)
# Request ID + structured access logging (outermost: see the stack note above).
app.add_middleware(RequestIdMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log internals server-side; return a generic 500 with the request ID."""
    request_id = getattr(request.state, "request_id", "-")
    app_logger.error(
        "event=unhandled_exception request_id=%s method=%s path=%s error=%s: %s",
        request_id,
        request.method,
        request.url.path,
        type(exc).__name__,
        exc,
    )
    headers = {} if request_id == "-" else {"X-Request-ID": request_id}
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Structured 429-free 422 without echoing raw internals."""
    request_id = getattr(request.state, "request_id", "-")
    app_logger.info(
        "event=validation_error request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "request_id": request_id},
    )


@app.exception_handler(OperationalError)
async def database_unavailable_handler(request: Request, exc: OperationalError):
    """Controlled 503 for database/connection failures — never a raw traceback.

    Only the exception *type* is logged, so connection strings, SQL statements
    and credentials never reach the client or the log.
    """
    request_id = getattr(request.state, "request_id", "-")
    app_logger.error(
        "event=database_error request_id=%s method=%s path=%s error=%s",
        request_id,
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    headers = {} if request_id == "-" else {"X-Request-ID": request_id}
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database temporarily unavailable",
            "request_id": request_id,
        },
        headers=headers,
    )


# --- Routers -----------------------------------------------------------------
app.include_router(music_router, prefix="/api/v1", tags=["music"])
app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(profile_router, prefix="/api/v1", tags=["profile"])
app.include_router(favorites_router, prefix="/api/v1", tags=["favorites"])
app.include_router(playlists_router, prefix="/api/v1", tags=["playlists"])
app.include_router(playlist_tracks_router, prefix="/api/v1", tags=["playlist-tracks"])
app.include_router(recently_played_router, prefix="/api/v1", tags=["recently-played"])


@app.get("/health", dependencies=[Depends(rate_limiter("health"))])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@app.get("/health/db", dependencies=[Depends(rate_limiter("health"))])
def database_health(db: Session = Depends(get_db)):
    """Readiness probe for the database.

    Declared as a plain ``def`` endpoint on purpose: FastAPI runs synchronous
    endpoints in a worker thread, whereas a synchronous SQLAlchemy call inside
    an ``async def`` endpoint would block the event loop for every other
    in-flight request.

    The response is deliberately coarse — status only.  Connection URLs,
    credentials and driver internals are never returned, and only the
    exception *type* is logged.
    """
    try:
        db.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }

    except Exception as exc:
        # Log the exception type only â€” never the connection URL or credentials.
        app_logger.error("event=database_health_check failed error=%s", type(exc).__name__)

        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        ) from exc
