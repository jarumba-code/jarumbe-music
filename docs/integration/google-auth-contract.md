# Google Sign-In + Supabase Auth — Backend Foundation

> Flow documentation and remaining configuration steps for the Google
> Sign-In + Supabase Auth foundation milestone in the Jarumba Music backend.

## Overview

The Jarumba Music backend authenticates users through **Supabase Auth**.
Google Sign-In is the initial provider.  The backend **does not** implement
OAuth directly; it only verifies the JWT that Supabase issues after a
successful sign-in.

## Full authentication flow

### Step 1 — Mobile app initiates sign-in

1. The mobile app uses the Supabase client SDK (configured with
   ``SUPABASE_URL`` and ``SUPABASE_ANON_KEY``).
2. The user taps "Sign in with Google".
3. The Supabase client SDK opens the Google OAuth consent screen (via Supabase
   Auth's hosted flow).

### Step 2 — Google → Supabase

1. The user authenticates with Google.
2. Google returns an OAuth token to Supabase.
3. Supabase verifies the token, creates or looks up the ``auth.users`` row,
   and issues a **session** consisting of:
   * An **access token** (a short-lived JWT signed by Supabase Auth — with the
     project's JWT Signing Keys (asymmetric, e.g. ES256) or, on legacy
     projects, the shared JWT secret (HS256)).
   * A **refresh token** (long-lived, used to get new access tokens).

### Step 3 — Supabase → Mobile app

1. The mobile app receives the access token and refresh token.
2. The mobile app stores them securely (platform secure storage).
3. The mobile app includes the access token on every request to the Jarumba
   backend as ``Authorization: Bearer <access_token>``.

### Step 4 — Mobile app → Jarumba backend

1. The mobile app sends a request to a protected endpoint (e.g.
   ``GET /api/v1/auth/me``).
2. The backend verifies the JWT.  Jarumba's Supabase project uses the
   **JWT Signing Keys** system, so verification is asymmetric and key
   material never needs to be configured:

   * The signing key is resolved from the token's ``kid`` against the
     project's public JWKS endpoint
     (``<SUPABASE_URL>/auth/v1/.well-known/jwks.json``); keys are cached and
     re-fetched on rotation (unknown ``kid``).
   * Algorithm allow-list: ``ES256`` only (blocks algorithm confusion).
   * Required claims are present (``sub``, ``aud``, ``role``, ``iss``,
     ``exp``).
   * ``exp`` is still in the future.
   * ``aud`` matches the Supabase project URL; ``iss`` matches
     ``<SUPABASE_URL>/auth/v1``.

   Legacy fallback: if only ``SUPABASE_JWT_SECRET`` is configured, the token
   is verified with the shared secret (``HS256``, required claims ``sub``,
   ``aud``, ``role``, ``email``, ``app_metadata``, ``user_metadata``,
   ``exp``).
3. The backend extracts ``sub`` — the authenticated Supabase user UUID.
4. The backend optionally ensures a ``profiles`` row exists (idempotent).
5. The backend returns the response (e.g. ``{ "id": "<uuid>" }`` for
   ``/auth/me``).

### Step 5 — Token refresh

1. When the access token expires, the mobile app uses the refresh token with
   the Supabase client SDK to get a new access token.
2. The backend is not involved in refresh — this stays on the Supabase / client
   side.

## What the backend **does not** do

* Does **not** implement the Google OAuth flow.
* Does **not** store Google tokens, refresh tokens, or any credentials.
* Does **not** trust client-supplied ``user_id`` values.
* Does **not** log token values.
* Does **not** require any new dependencies beyond PyJWT.

## Required configuration

### Supabase Dashboard

1. **Enable Google provider.**  Authentication → Providers → Google → Enable.
   Enter the Google Client ID and Client Secret (from Google Cloud Console).
   Configure the redirect URL that Supabase provides (shown in provider
   settings).

2. **JWT signing (JWT Signing Keys).**  Jarumba's project uses the JWT
   Signing Keys system: Supabase Auth signs access tokens with an asymmetric
   key (ES256) and publishes the public keys at
   ``<SUPABASE_URL>/auth/v1/.well-known/jwks.json``.  The backend requires
   **no key configuration** — it fetches the public keys itself and handles
   rotation automatically.  Do not delete the legacy JWT secret in the
   dashboard while the fallback ``SUPABASE_JWT_SECRET`` is still configured
   anywhere; retire both together in a coordinated change.

3. **Note the project URL and anon key.**  Found on the project's general
   settings page.  ``SUPABASE_URL`` — project URL (client-safe).
   ``SUPABASE_ANON_KEY`` — anonymous / publishable key (client-safe).  Both go
   into the mobile app's Supabase client configuration.

4. **RLS (future work).**  RLS agent configures Row Level Security on
   ``profiles``, ``favorites``, ``playlists``, ``playlist_tracks``,
   ``recently_played``.  RLS agent may set up an ``auth.users`` insert trigger
   to create ``profiles`` rows automatically.

### Google Cloud Console

1. **Create an OAuth 2.0 Client ID.**  APIs & Services → Credentials → OAuth
   2.0 Client ID (Web application).  Add the authorized redirect URI that
   Supabase provides.

2. **Configure the OAuth consent screen.**  Choose user type (typically
   External for testing).  Add scopes ``email`` and ``profile``.  Add test
   users if the app is in testing mode.

3. **Copy Client ID and Client Secret** into the Supabase Dashboard's Google
   provider settings.

### Backend ``.env``

Add to ``services/api/.env`` (gitignored): ``SUPABASE_URL`` (Supabase project
URL — **required**: it drives JWKS verification and the expected ``aud``/``iss``)
and ``SUPABASE_ANON_KEY`` (anonymous / publishable key).
``SUPABASE_JWT_SECRET`` (shared JWT secret from Supabase Dashboard,
server-side only) is **optional** and only used as the legacy ``HS256``
fallback when ``SUPABASE_URL`` is not set.

**Never** commit these values or log them.  ``.env`` is already gitignored.

## Session expiry model

Jarumba is a **native mobile application**. Authentication uses the Supabase
session model — **no custom cookies and no custom session-expiration logic**.

1. **Finite expiry.** Supabase access JWTs always carry a finite ``exp``.
   The project keeps the Supabase-recommended default (**1 hour**). Do not
   change it without a documented reason.
2. **Client refresh.** The mobile client uses the Supabase SDK's **automatic
   session refresh**: when the access token expires, the SDK transparently
   exchanges the refresh token for a new access token and the app retries
   with the fresh token. The backend only ever sees access tokens.
3. **Secure persistence.** The mobile client stores the Supabase session
   (access + refresh tokens) in secure mobile storage (e.g. Expo SecureStore /
   iOS Keychain / Android Keystore). The backend stores **nothing**: no
   refresh tokens, no sessions, no cookie state.
4. **Verification on every request.** FastAPI validates the access JWT's
   signature, expiry, audience, issuer and required claims on **every**
   protected request. An expired, tampered, or wrongly-signed token is
   rejected with **401** — never trusted, never silently refreshed.
5. **No refresh-token handling in the backend.** Refresh flows belong to the
   Supabase Auth service and the mobile SDK. The FastAPI layer never receives,
   stores, or acts on refresh tokens.
6. **No cookies.** Because the native flow is Bearer-token based, there are no
   authentication cookies and therefore no cookie Max-Age/Expires settings to
   manage. Do not introduce cookie-based sessions for the mobile app.
7. **Future web/SSR components** (if any): treat any cookie lifetime there as
   a separate decision from the Supabase session lifetime; it must not drive
   or constrain the mobile session model.

## Verification checklist

### Automated (unit tests)

``test_auth.py`` covers: valid token → expected user UUID; missing token → 401;
malformed token → 401; expired token → 401; wrong-secret token → 401; wrong-
audience token → 401 (verified in ``verify_supabase_token`` unit tests); non-
Bearer scheme → 401; unconfigured JWT secret → 500; profile sync: creates when
absent, idempotent, multiple users, persists writable fields.  JWKS-mode tests
(offline, locally generated P-256 keys) cover: valid ES256 token, invalid
signature, expired, wrong issuer, wrong audience, HS256 algorithm-confusion
rejection, unknown ``kid``, key rotation (new ``kid`` accepted, removed key
rejected), missing required claims, JWKS-preferred-over-secret precedence, and
the JWKS client URI/caching setup.  A live probe of the real project JWKS
endpoint additionally confirmed that a forged ES256 token is rejected by the
actually published signing key.

### Manual (live verification)

1. Start the backend with the real Supabase configuration in ``.env``.
2. Obtain a real access token from Supabase (via the mobile app or the Supabase
   client SDK in a test script).
3. Call ``GET /api/v1/auth/me`` with the real token → expect 200 with the UUID.
4. Call ``GET /api/v1/auth/me`` without a token → expect 401.
5. Call ``GET /api/v1/auth/me`` with a tampered/expired token → expect 401.
6. Confirm no JWT values, secrets, or credentials appear in logs or response
   bodies.
