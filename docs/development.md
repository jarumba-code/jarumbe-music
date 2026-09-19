# Development

## Environment configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | **Normal application database configuration.** Used by the API at runtime (`app/config.py`). |
| `JARUMBA_LIVE_DATABASE_URL` | **Explicitly provided database URL used ONLY when a human deliberately enables live RLS verification.** Never read by the application. |

**Rule:** the test suite must never infer the live-test target from
`DATABASE_URL`. There is no fallback - live database tests can only ever
target the database named by `JARUMBA_LIVE_DATABASE_URL`, which is set by
hand, deliberately, for a controlled verification run.

## Test layers

1. **Default suite (hermetic).** `python -m pytest -q` - unit and mocked
   integration tests only. SQLite in-memory database, mocked auth tokens,
   mocked Jamendo transport. Never opens a network or database connection.
2. **Live RLS verification (opt-in).**
   `services/api/tests/integration/test_rls_live.py` - skipped unless **both**
   `JARUMBA_RUN_LIVE_RLS=1` **and** `JARUMBA_LIVE_DATABASE_URL` are set.
   Reserved for controlled private verification before launch.

## Running the live RLS suite (deliberate, controlled runs only)

1. Set `JARUMBA_RUN_LIVE_RLS=1`.
2. Set `JARUMBA_LIVE_DATABASE_URL` to the PostgreSQL URL a human has
   explicitly designated for verification.
3. `python -m pytest tests/integration/test_rls_live.py -q`
4. Unset both variables afterwards.

Every live test runs inside a single transaction that is rolled back in
teardown, so no test identities or rows persist. Live tests never weaken RLS
or touch production configuration; a missing explicit URL always results in a
skip, never a fallback connection.
