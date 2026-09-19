from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from uuid import UUID

import jwt
from jwt import PyJWKClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.profile import Profile

# Algorithms accepted in each verification mode.  These are strict allow-lists;
# anything else (including ``none``) is rejected by PyJWT before any claim is
# trusted.
_ASYMMETRIC_ALGORITHMS = ["ES256"]
_LEGACY_ALGORITHMS = ["HS256"]


class AuthVerificationError(Exception):
    """Raised when a Supabase JWT cannot be verified or is unacceptable."""


def create_jwks_client(supabase_url: str) -> PyJWKClient:
    """Build a cached ``PyJWKClient`` for the project's public signing keys.

    PyJWKClient caches fetched keys and transparently re-fetches when a token
    carries an unknown ``kid`` â€” which is exactly how Supabase key rotation
    must be handled (new key published to the JWKS endpoint, old keys remain
    until revoked).  One client instance should be reused across requests.
    """
    if not supabase_url:
        raise AuthVerificationError("SUPABASE_URL is not configured")
    jwks_uri = supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_uri, cache_keys=True)


def verify_supabase_token_jwks(
    token: str,
    jwks_client: PyJWKClient,
    audience: str,
) -> dict:
    """Verify a Supabase access token signed with asymmetric signing keys.

    This is the verification mode for the Supabase JWT Signing Keys system
    (ES256 / P-256 public keys published at ``/auth/v1/.well-known/jwks.json``):

    * Only ``ES256`` is accepted â€” the algorithm allow-list prevents
      algorithm-confusion attacks.
    * The signing key is resolved by the token's ``kid`` from the cached JWKS;
      unknown ``kid`` triggers a safe re-fetch (rotation).
    * Required claims: ``sub``, ``aud``, ``role``, ``iss``, ``exp``.
    * ``exp`` must be in the future (enforced by PyJWT).
    * ``aud`` must equal the project URL; ``iss`` must equal
      ``<project-url>/auth/v1``.

    No private key material is ever handled â€” only the public JWKS.
    """
    if jwks_client is None:
        raise AuthVerificationError("JWKS client is not configured")

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
    except (jwt.PyJWKClientError, jwt.DecodeError) as exc:
        # Unknown kid absent even after re-fetch, unreachable JWKS endpoint,
        # or a structurally malformed token (e.g. not a JWT at all).
        raise AuthVerificationError("Invalid token") from exc

    expected_issuer = audience.rstrip("/") + "/auth/v1"
    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=_ASYMMETRIC_ALGORITHMS,
            audience=audience,
            issuer=expected_issuer,
            options={
                "require": [
                    "sub",
                    "aud",
                    "role",
                    "iss",
                    "exp",
                ],
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthVerificationError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthVerificationError("Invalid token") from exc
    except ValidationError as exc:
        raise AuthVerificationError("Invalid token claims") from exc

    return claims


def verify_supabase_token(
    token: str,
    secret: str,
    audience: str,
) -> dict:
    """Verify a legacy Supabase HS256 JWT and return its decoded claims.

    .. deprecated::
        Only used when the project still signs with the legacy shared JWT
        secret.  Jarumba's current Supabase project uses the JWT Signing Keys
        system (see :func:`verify_supabase_token_jwks`); this path is retained
        as a verified fallback until the legacy secret is fully retired.

    Follows the contract in ``docs/integration/auth-rLS-contract.md``:

    * Algorithm: HS256.
    * The token must be signed with ``secret``.
    * Required claims (``sub``, ``aud``, ``role``, ``email``,
      ``app_metadata``, ``user_metadata``, ``exp``) must be present.
    * ``exp`` must still be in the future (enforced by PyJWT).
    * ``aud`` must match the configured Supabase project URL.

    Raises :class:`AuthVerificationError` for any failure.  Token values are
    never logged or returned to callers beyond the small, client-safe error
    messages produced by the HTTP layer.
    """
    if not secret:
        raise AuthVerificationError("JWT secret is not configured")

    # When no project URL is configured the audience claim cannot be checked
    # against an expected value.  PyJWT 2.11 treats ``audience=None`` as
    # "validate against None", so the check must be disabled explicitly
    # (``verify_aud: False``) rather than passing ``audience=None``.
    decode_options = {
        "require": [
            "sub",
            "aud",
            "role",
            "email",
            "app_metadata",
            "user_metadata",
            "exp",
        ],
    }
    if not audience:
        decode_options["verify_aud"] = False

    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=_LEGACY_ALGORITHMS,
            audience=audience or None,
            options=decode_options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthVerificationError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthVerificationError("Invalid token") from exc
    except ValidationError as exc:
        raise AuthVerificationError("Invalid token claims") from exc

    return claims


def get_authenticated_user_id(claims: dict) -> UUID:
    """Extract and validate the authenticated user UUID from verified claims.

    The Supabase user UUID is carried in the ``sub`` claim.  It must be a
    parseable UUID; anything else is treated as an invalid token.
    """
    raw = claims.get("sub")
    if not raw or not isinstance(raw, str):
        raise AuthVerificationError("Token is missing the 'sub' claim")

    try:
        return UUID(raw)
    except ValueError as exc:
        raise AuthVerificationError("Token 'sub' is not a valid UUID") from exc


def ensure_profile_exists(db: Session, user_id: UUID) -> Profile:
    """Idempotently ensure a ``profiles`` row exists for the given user.

    Safe to call repeatedly â€” if the row already exists it is returned
    as-is.  Only Jarumba presentation fields are touched; no credentials are
    stored or read.  ``created_at`` / ``updated_at`` are left to their
    server-side defaults.

    Two first requests from the same brand-new user can race on the primary
    key.  The insert is therefore *resolved* rather than surfaced: on an
    integrity violation the row committed by the other request is re-read and
    returned, so a concurrent duplicate insert never becomes an uncontrolled
    500 and never leaves a partial write behind.
    """
    uid = str(user_id)
    row = db.execute(
        select(Profile).where(Profile.id == uid)
    ).scalar_one_or_none()

    if row is not None:
        return row

    profile = Profile(id=uid)
    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.execute(
            select(Profile).where(Profile.id == uid)
        ).scalar_one_or_none()
        if row is None:
            # Not a lost race (for example the referenced auth.users row is
            # absent): re-raise so the caller reports a controlled error.
            raise
        return row
    db.refresh(profile)
    return profile

@lru_cache(maxsize=4)
def _jwks_client_for(supabase_url: str) -> PyJWKClient:
    """One cached JWKS client per project URL - never per request."""
    return create_jwks_client(supabase_url)

