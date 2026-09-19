# Auth + RLS Integration Contract

> Coordination contract between the **Auth agent** (this document's author)
> and the **RLS agent**.  Read this before modifying authentication,
> authorization, or row-level security code in the Jarumba Music backend.

## Purpose

This document defines:

* How Jarumba authenticates requests using Supabase Auth.
* How the authenticated Supabase user identity flows into the rest of the
  system.
* Which changes belong to the Auth agent and which belong to the RLS agent.
* The minimal, documented changes that either agent may make to the other's
  area when strictly necessary.

## High-level flow

1. A client authenticates through **Supabase Auth** (Google Sign-In for the
   initial release).
2. Supabase issues the client a short-lived **access token** (a JWT) and a
   refresh token.
3. The client sends that access token to Jarumba's FastAPI backend on every
   protected request as ``Authorization: Bearer <token>``.
4. Jarumba verifies the JWT signature using the **Supabase JWT secret**
   (server-side only) and extracts the authenticated user UUID from the JWT's
   ``sub`` claim.
5. Downstream handlers use that verified UUID as the authenticated user identity.
6. Row Level Security on Supabase PostgreSQL further restricts access to
   user-owned data; the RLS agent makes the authenticated UUID visible to
   Postgres in the required way.

## Identity model

* Supabase Auth is the **single source of truth** for user identity.
* The authenticated user UUID is **always** ``auth.users.id``, exposed in the
  JWT as ``sub``.
* Jarumba **never** trusts a client-supplied ``user_id``.  The only trusted
  identity for a request comes from a verified JWT.
* Jarumba stores **no passwords, OAuth tokens, or other credentials**.
* The ``profiles`` table's primary key is the ``auth.users.id`` and it holds
  only Jarumba-specific presentation data (``display_name``, ``avatar_url``).
* Supabase owns the ``auth`` schema and ``auth.users``.  Jarumba references
  ``auth.users`` in metadata **only** for foreign-key resolution and never
  migrates or modifies it.

## Required server-side configuration

| Setting | Purpose | Visibility |
| --- | --- | --- |
| ``SUPABASE_URL`` | Supabase project URL (used by clients and backend) | Client-safe |
| ``SUPABASE_ANON_KEY`` | Supabase anonymous / publishable key | Client-safe |
| ``SUPABASE_JWT_SECRET`` | Symmetric key used to verify access-token signatures | **Server-side only** |

The **JWT secret must never** be shipped to mobile clients, committed to source
control, or logged.  The client-safe settings (``SUPABASE_URL``,
``SUPABASE_ANON_KEY``) are used by the Supabase client on the mobile app to
perform sign-in; the mobile app does **not** receive the JWT secret.
## JWT verification (Auth agent)

Jarumba uses **PyJWT** (already available) to verify the JWT:

* Algorithm: ``HS256`` (Supabase default).
* Secret: ``SUPABASE_JWT_SECRET``.
* Verification checks:
  * Valid JWT structure and signature.
  * Required claims present: ``sub``, ``aud``, ``role``, ``email``,
    ``app_metadata``, ``user_metadata``, ``exp``.
  * ``exp`` is still in the future — handled by PyJWT.
  * ``aud`` matches the Supabase project URL, so tokens are project-scoped.
* A failed verification returns **HTTP 401 Unauthorized** with a generic,
  client-safe message.
* Verified or failed tokens are **not logged**.  Only the fact that
  authentication passed or failed is logged, and even then token values are
  never included.

## Profile synchronization (Auth agent)

When a request is authenticated, Jarumba can ensure a ``profiles`` row exists
for that user in an **idempotent** way:

* ``services.auth.ensure_profile_exists(db, user_id)`` creates a profile row if
  one does not already exist, and is safe to call repeatedly.
* This is a server-side convenience so downstream routes and any future RLS
  configuration do not encounter missing profile rows.
* It is **not** the only mechanism: a Supabase ``auth.users`` insert trigger can
  also create ``profiles`` rows at the database level.  Both can run
  simultaneously — the row already existing is fine.
* Profile rows are created with server-side defaults for ``created_at`` /
  ``updated_at``; no credentials are stored.

## RLS boundary (RLS agent)

The RLS agent owns:

* Row Level Security policies on ``profiles``, ``favorites``, ``playlists``,
  ``playlist_tracks``, ``recently_played``.
* Any database trigger that creates ``profiles`` from ``auth.users``.
* Ensuring the API's database session participates in RLS correctly — for
  example, by setting the authenticated user's JWT claims on the session so that
  ``auth.uid()`` reflects the authenticated user for each request.

If the RLS agent needs the authenticated user UUID to be made available to
Postgres in a specific way, it documents that here and the Auth agent exposes
it through the smallest possible change to the auth dependency.  The Auth agent
**does not** modify RLS policies, migration files, or the ``auth`` schema.

## Public API surface (foundation milestone)

| Endpoint | Protection | Notes |
| --- | --- | --- |
| ``GET /health`` | None | Health check |
| ``GET /health/db`` | None | Database connectivity check |
| ``GET /api/v1/music/search`` | None | Public music search |
| ``GET /api/v1/auth/me`` | **Bearer JWT required** | Returns ``{ "id": "<uuid>" }``, 401 when unauthenticated |

A minimal internal test endpoint may be added for verification; it must never
expose secrets or credentials.

## Error contract

* Missing, invalid, expired, or mismatched token → **401 Unauthorized**.
* A server-side verification error that is not the client's fault → **500
  Internal Server Error** with a non-revealing message.
* All error responses must avoid leaking JWT payloads, secrets, internal paths,
  or database details.

## Testing

Auth tests are **mocked and deterministic**:

* A fixture builds signed Supabase-style JWTs for a known ``sub``, ``aud``,
  and ``role`` using a known secret.
* Coverage:
  * Valid token → expected user UUID.
  * Missing token → 401.
  * Malformed token → 401.
  * Expired token → 401.
  * Signature mismatch (wrong secret) → 401.
  * Wrong scheme (e.g. ``Basic`` instead of ``Bearer``) → 401.
  * Missing server-side JWT secret → 500.
* Profile synchronization is tested via the ``ensure_profile_exists`` unit
  function directly: creates when absent, is idempotent, uses server defaults,
  and does not damage existing rows.
* No real Supabase HTTP calls happen in unit tests.  Full live verification is a
  documented manual step.
* Tests **never** log or assert the contents of any real secret.

## Future extension

* Additional providers (e.g. Apple) can be added in Supabase Auth without any
  change to Jarumba's backend, because the backend only verifies the Supabase
  JWT.
* Refresh-token handling and rotation stay on the Supabase / client side.
* A dedicated profile update endpoint may be added later using the same
  ``get_current_user_id`` dependency.

