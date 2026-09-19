# ADR 0002: Supabase Auth + Google Sign-In (Backend Foundation)

> Archived rewrite of the foundation decisions behind the Supabase Auth +
> Google Sign-In implementation in the Jarumba Music FastAPI backend.
> This ADR supersedes the empty placeholder that previously existed at this
> path and reflects the code now present in ``app/services/auth.py``,
> ``app/api/routes/auth.py``, and the contracts in
> ``docs/integration/``.

## Status

Accepted — implemented.

## Context

The Jarumba Music backend is a FastAPI service that must authenticate
requests from the mobile client using Supabase Auth.  Google Sign-In is the
initial provider.  The backend is **not** building its own user store,
password database, OAuth flows, or token issuing.  Its only authentication
responsibility is to verify the JWT that a client obtained from Supabase Auth
and to expose the authenticated Supabase user identity to downstream routes.

## Decision

1. **Supabase Auth is the single source of truth** for user identity.
   The authenticated user UUID is always ``auth.users.id``, carried in the
   JWT's ``sub`` claim.  Jarumba never trusts a client-supplied ``user_id``.

2. **Jarumba verifies the Supabase JWT**, it does not issue tokens.
   Verification is performed with **PyJWT** using the **HS256** algorithm and
   the server-side **Supabase JWT secret** (``SUPABASE_JWT_SECRET``).  The
   mobile client never receives this secret.

3. **Client-safe config** is limited to ``SUPABASE_URL`` and
   ``SUPABASE_ANON_KEY``.  The JWT secret is server-side only and is never
   logged, committed, or shipped to clients.

4. **The ``/auth/me`` endpoint is the minimal protected surface** for this
   foundation milestone: ``GET /api/v1/auth/me`` returns ``{ "id": "<uuid>" }``
   and requires a valid Bearer JWT.  Missing, malformed, expired, or otherwise
   unverifiable tokens return **401 Unauthorized**.

5. **Profile synchronization is idempotent and server-side.**
   ``services.auth.ensure_profile_exists(db, user_id)`` creates a ``profiles``
   row if one does not already exist and is safe to call repeatedly.  No
   credentials are stored.  A Supabase ``auth.users`` insert trigger is the
   complementary database-level mechanism; both can run simultaneously.

6. **Auth and RLS work are separated by contract.**
   The Auth agent owns JWT verification, the ``/auth/me`` endpoint, and the
   profile-sync utility.  The RLS agent owns RLS policies, the ``auth.users``
   insert trigger, and making the authenticated UUID visible to Postgres.  The
   coordination contract lives in ``docs/integration/auth-rLS-contract.md``.

7. **No custom JWT code and no custom crypto.**
   The backend relies on PyJWT (already available) and the Supabase JWT secret
   for verification.  Token values are never logged.

## Consequences

### Positive

* The mobile client can authenticate entirely through Supabase (Google Sign-In
  configured in the Supabase Dashboard) without any changes to the backend once
  the JWT secret is configured server-side.
* Adding future providers (e.g. Apple) only requires configuration in Supabase
  Auth — the backend only verifies the Supabase JWT.
* Profile sync is idempotent, so repeated authenticated requests do not create
  duplicate rows or errors.
* The contract document makes the Auth/RLS boundary explicit and minimizes
  coordination risk.

### Negative / trade-offs

* The backend depends on the Supabase JWT secret being configured and kept
  secret.  Loss or rotation of the secret requires coordinated rollout.
* The foundation milestone does **not** implement refresh-token handling,
  profile update endpoints, or RLS enforcement end-to-end; those are future
  work.
* Live end-to-end verification (real Google Sign-In → Supabase → backend)
  requires manual steps in the Supabase Dashboard and Google Cloud Console and
  is documented separately.

## Related documents

* ``docs/integration/auth-rLS-contract.md`` — Auth ↔ RLS coordination contract.
* ``docs/integration/google-auth-contract.md`` — Google Sign-In + Supabase Auth
  flow and remaining dashboard/console steps.
* ``app/services/auth.py`` — JWT verification and profile sync implementation.
* ``app/api/routes/auth.py`` — ``GET /api/v1/auth/me`` and the
  ``get_current_user_id`` dependency.
* ``app/config.py`` — ``supabase_jwt_secret`` setting.

