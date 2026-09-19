"""Authentication routes.

Foundation milestone surface:

* ``GET /api/v1/auth/me`` — returns the authenticated Supabase user UUID
  (requires a valid Bearer JWT).  Nothing else is exposed here.

The verified user identity is produced by a FastAPI dependency
(:func:`get_current_user_id`).  Verification mode:

* **JWT Signing Keys (current).**  When ``SUPABASE_URL`` is configured the
  Bearer token is verified against the project's public signing keys via the
  JWKS endpoint (ES256).  Keys are cached and re-fetched on key rotation.
* **Legacy JWT secret (fallback).**  When only ``SUPABASE_JWT_SECRET`` is
  configured, the token is verified with the shared secret (HS256).

No private key material and no token values are ever logged.  See
``app/services/auth.py`` and ``docs/integration/google-auth-contract.md``.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import Settings, get_settings
from app.schemas.auth import AuthMeResponse
from app.api.deps import rate_limiter
from app.services.auth import (
    AuthVerificationError,
    create_jwks_client,
    get_authenticated_user_id,
    verify_supabase_token,
    verify_supabase_token_jwks,
)

router = APIRouter()
_bearer_documentation = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def _jwks_client_for(supabase_url: str) -> PyJWKClient:
    """One cached JWKS client per project URL — never per request."""
    return create_jwks_client(supabase_url)


def get_current_user_id(
    request: Request,
    settings: Settings = Depends(get_settings),
    _credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_documentation),
) -> str:
    """FastAPI dependency that verifies the Bearer JWT and returns the user UUID.

    The authenticated user identity is taken **only** from the verified JWT's
    ``sub`` claim.  No client-supplied ``user_id`` is trusted.
    """
    raw = request.headers.get("Authorization", "")
    if not raw.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = raw[len("Bearer "):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    try:
        if settings.supabase_url:
            claims = verify_supabase_token_jwks(
                token=token,
                jwks_client=_jwks_client_for(settings.supabase_url),
                audience=settings.supabase_url,
            )
        elif settings.supabase_jwt_secret:
            claims = verify_supabase_token(
                token=token,
                secret=settings.supabase_jwt_secret,
                audience=settings.supabase_url,
            )
        else:
            raise AuthVerificationError("Authentication is not configured")
    except AuthVerificationError as exc:
        detail = str(exc)
        if "not configured" in detail:
            raise HTTPException(status_code=500, detail="Authentication service unavailable") from exc
        raise HTTPException(status_code=401, detail=detail) from exc

    return str(get_authenticated_user_id(claims))


@router.get(
    "/auth/me",
    response_model=AuthMeResponse,
    dependencies=[Depends(rate_limiter("auth", fail_closed=True))],
)
async def auth_me(
    current_user_id: str = Depends(get_current_user_id),
) -> AuthMeResponse:
    """Return the authenticated Supabase user UUID.

    Requires a valid Bearer JWT in the ``Authorization`` header.  Returns
    ``401 Unauthorized`` when no token is presented, the token is malformed,
    expired, signed with a wrong secret, or otherwise unverifiable.

    Rate limiting is declared as a route-level dependency, which FastAPI
    resolves *before* the endpoint's own parameters.  It therefore runs before
    token verification: repeated malformed / expired / wrong-signature /
    unknown-``kid`` tokens are charged to the unauthenticated IP bucket and
    eventually answered with 429 rather than being able to probe the verifier
    for free.  That limiter fails closed (503) when Redis is unavailable.
    """
    return AuthMeResponse(id=current_user_id)
