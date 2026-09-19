"""Root-level pytest configuration.

The unit tests introspect SQLAlchemy metadata and the Alembic revision graph;
they never need a live database.  The application engine is created at import
time in :mod:`app.database` from ``settings.database_url``, so we pin that to
an in-memory SQLite URL *before* the app is imported.

This is deliberately an assignment rather than ``os.environ.setdefault``: the
tests must be hermetic.  If a developer happens to have a ``DATABASE_URL`` in
their shell (e.g. an unreachable host from a previous command), ``setdefault``
would leave it in place and every test run would pay the connection timeout.
Tests that genuinely need a different URL set ``DATABASE_URL`` explicitly in
the subprocess environment they construct (see ``test_migrations.py``).
"""

import os

# Pin the application engine to SQLite for the test session.  Must happen
# before any test module imports ``app.database``; pytest loads this
# conftest.py first.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Ensure JAMENDO_CLIENT_ID has a non-empty default for tests that don't
# override it; the route-level "missing credential" test overrides settings
# explicitly.
os.environ.setdefault("JAMENDO_CLIENT_ID", "test_client_id_for_testing_only")

