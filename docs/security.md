# Jarumba Music — Security Notes

## `rls_auto_enable` — admin guard, locked down (2026-09-17)

**What it is.** `jarumba_admin.rls_auto_enable()` is the body of the
`ensure_rls` event trigger (`ddl_command_end`): it automatically enables row
level security on every new table created in the `public` schema. It is a
deliberate defense-in-depth guard: no table can ever silently ship without
RLS. It is owned by `postgres` and runs with definer rights so the guard
always succeeds regardless of which role runs the DDL.

**Finding.** The Supabase security advisor flagged it as
`SECURITY DEFINER` + `executable by anon` + reachable via
`/rest/v1/rpc/rls_auto_enable`. Root cause: PostgreSQL's default function ACL
grants `EXECUTE` to `PUBLIC`, so PostgREST exposed the guard to
`anon`/`authenticated`. The function is only meaningful inside an event
trigger (`pg_event_trigger_ddl_commands()` fails outside that context), so no
client ever has a legitimate reason to call it.

**Remediation** (Alembic migration `b4e1f9a2c7d3`, applied):

1. `REVOKE EXECUTE` on the function from `PUBLIC`, `anon` and `authenticated`.
2. Relocated the function from the Data API-exposed `public` schema to the
   dedicated `jarumba_admin` schema, so it is unreachable via PostgREST by
   design. Event triggers bind to the function OID, which a schema move
   preserves — the `ensure_rls` guard keeps firing (verified live).

**Intentional state (documented reason for definer rights):** the function
remains `SECURITY DEFINER` on purpose — it must be able to `ALTER TABLE ...
ENABLE ROW LEVEL SECURITY` on tables created by any role. It is intentionally
**not** executable by `anon`/`authenticated`: `has_function_privilege` returns
`False` for all three, and it lives outside the API-exposed schema.

**Rules for future work:**

- Never re-grant `EXECUTE` on `jarumba_admin.*` functions to
  `anon`/`authenticated`/`PUBLIC`.
- New privileged helper functions belong in `jarumba_admin`, not `public`.
- `jarumba_admin` must never be added to the PostgREST "Exposed schemas"
  setting in the Supabase dashboard.

## API rate limiting — IMPLEMENTED (Python/FastAPI backend)

The active backend (`services/api`, Python/FastAPI) enforces fixed-window rate
limits (default window 60s) via `app/services/rate_limit.py`, attached as a
route-level dependency so the limiter runs **before** JWT verification:

* **Identity**: authenticated requests are keyed by the verified JWT `sub`;
  anything unauthenticated — including malformed, expired, wrong-signature or
  unknown-`kid` tokens — is keyed by client IP.  Invalid tokens therefore
  cannot bypass the limiter.
* **Buckets** (requests/minute): global 120 authenticated / 30 anonymous;
  music search 30; favorites 60; playlists 30; playlist-track operations 60;
  recently played 60; profile 60; auth-sensitive (`/auth/me`) 10; health 60.
* **Backend**: counters live in Redis (`REDIS_URL`) with `INCR`+`EXPIRE`
  executed as one atomic Lua script, and explicit connect/command timeouts.
  A deployed environment must set `REDIS_URL` (or explicitly set
  `RATE_LIMIT_ALLOW_MEMORY_FALLBACK=true`); it never silently falls back to
  per-process counters — `require_shared_rate_limit_backend` fails fast.
* **Trusted proxy**: `X-Forwarded-For` is only honoured when
  `TRUST_PROXY_HEADERS=true` AND the immediate peer is listed in
  `TRUSTED_PROXY_IPS`; `TRUSTED_PROXY_COUNT` right-hand hops are skipped.
  Spoofed forwarding headers cannot mint fresh buckets.
* **Failure policy**: Redis outages fail **open** for normal endpoints and
  fail **closed** (503) for auth-sensitive endpoints, so an attacker cannot
  knock Redis over to lift the auth rate limit.
* **Responses**: `429` returns the standard `{"detail": ...}` JSON shape with
  `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
  `X-RateLimit-Scope` headers (all CORS-exposed).

Coverage: `tests/unit/test_rate_limit.py` (39 tests).


