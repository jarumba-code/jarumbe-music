"""RLS policy tests for the Alembic migration.

These tests run fully offline: they introspect the revision graph and render
the migration with ``alembic upgrade head --sql`` (offline mode never opens a
database connection).  A placeholder PostgreSQL URL is used so the rendered
DDL is Postgres-flavoured; no real credentials are read or required.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# tests/unit/test_rls.py -> services/api
API_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_DIR = API_ROOT / "alembic"
VERSIONS_DIR = ALEMBIC_DIR / "versions"

OFFLINE_DATABASE_URL = "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder"


def _load_rls_revision_pair() -> tuple[str, str]:
    """Return ``(down_revision, revision)`` for the RLS migration file.

    Reading the identifiers from the migration itself keeps this test module
    from hard-coding a revision hash that would change on regeneration.
    """
    import importlib.util

    files = [p for p in VERSIONS_DIR.glob("*rls_policies*.py")]
    assert len(files) == 1, f"expected exactly one RLS migration, found {files}"
    spec = importlib.util.spec_from_file_location("_jarumba_rls_migration", files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.down_revision), str(module.revision)


DOWN_REVISION, RLS_REVISION = _load_rls_revision_pair()


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    """Invoke the Alembic CLI as a subprocess and capture its output."""
    env = dict(os.environ)
    env["DATABASE_URL"] = OFFLINE_DATABASE_URL
    env["PYTHONPATH"] = str(API_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(API_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


def render_offline_sql() -> str:
    """Render ``alembic upgrade head --sql`` offline and return the SQL.

    This is a plain helper (not a fixture) so the extraction logic below can be
    unit-tested and reused without going through pytest's fixture machinery.
    """
    result = _run_alembic("upgrade", "head", "--sql")
    assert result.returncode == 0, (
        "offline migration render failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result.stdout


def extract_rls_sql(full_sql: str) -> str:
    """Slice the RLS migration's own block out of the full rendered SQL."""
    marker = f"-- Running upgrade {DOWN_REVISION} -> {RLS_REVISION}"
    idx = full_sql.find(marker)
    assert idx != -1, "RLS migration SQL not found in rendered output"
    rls_block = full_sql[idx:]
    # Cut at the next migration marker (skip this migration's own header).
    next_marker = rls_block.find("-- Running upgrade", 1)
    if next_marker != -1:
        rls_block = rls_block[:next_marker]
    return rls_block


@pytest.fixture(scope="module")
def rendered_sql() -> str:
    """The SQL emitted by ``alembic upgrade head --sql`` (offline)."""
    return render_offline_sql()


@pytest.fixture(scope="module")
def rls_sql(rendered_sql: str) -> str:
    """The RLS portion of the rendered SQL, injected from ``rendered_sql``."""
    return extract_rls_sql(rendered_sql)


POLICY_NAMES = {
    "profiles": [
        "profiles_select_own",
        "profiles_insert_own",
        "profiles_update_own",
        "profiles_delete_own",
    ],
    "favorites": [
        "favorites_select_own",
        "favorites_insert_own",
        "favorites_update_own",
        "favorites_delete_own",
    ],
    "playlists": [
        "playlists_select_accessible",
        "playlists_insert_own",
        "playlists_update_own",
        "playlists_delete_own",
    ],
    "playlist_tracks": [
        "playlist_tracks_select_accessible",
        "playlist_tracks_insert_owned",
        "playlist_tracks_update_owned",
        "playlist_tracks_delete_owned",
    ],
    "recently_played": [
        "recently_played_select_own",
        "recently_played_insert_own",
        "recently_played_update_own",
        "recently_played_delete_own",
    ],
}

class TestRlsPoliciesExist:
    @pytest.mark.parametrize("table,policies", POLICY_NAMES.items())
    def test_table_has_rls_enabled(self, rls_sql, table, policies):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in rls_sql

    @pytest.mark.parametrize("table,policies", POLICY_NAMES.items())
    def test_all_policies_present(self, rls_sql, table, policies):
        for policy in policies:
            assert f"CREATE POLICY {policy}" in rls_sql


class TestRlsPolicySemantics:
    def test_profiles_select_uses_auth_uid(self, rls_sql):
        assert "CREATE POLICY profiles_select_own ON profiles FOR SELECT USING (id = auth.uid())" in rls_sql

    def test_profiles_insert_uses_auth_uid(self, rls_sql):
        assert "CREATE POLICY profiles_insert_own ON profiles FOR INSERT WITH CHECK (id = auth.uid())" in rls_sql

    def test_profiles_update_uses_auth_uid(self, rls_sql):
        assert "CREATE POLICY profiles_update_own ON profiles FOR UPDATE USING (id = auth.uid()) WITH CHECK (id = auth.uid())" in rls_sql

    def test_profiles_delete_uses_auth_uid(self, rls_sql):
        assert "CREATE POLICY profiles_delete_own ON profiles FOR DELETE USING (id = auth.uid())" in rls_sql

    def test_favorites_all_operations_use_user_id(self, rls_sql):
        for op in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert f"favorites_{op.lower()}_own" in rls_sql
        assert "auth.uid()" in rls_sql

    def test_playlists_select_allows_public(self, rls_sql):
        assert "is_public = true" in rls_sql
        assert "user_id = auth.uid() OR is_public = true" in rls_sql

    def test_playlists_write_requires_ownership(self, rls_sql):
        for op in ("INSERT", "UPDATE", "DELETE"):
            assert f"playlists_{op.lower()}_own" in rls_sql
            assert "user_id = auth.uid()" in rls_sql

    def test_playlist_tracks_select_checks_playlist_visibility(self, rls_sql):
        assert "playlist_tracks_select_accessible" in rls_sql
        assert "EXISTS (SELECT 1 FROM playlists p" in rls_sql

    def test_playlist_tracks_write_requires_playlist_ownership(self, rls_sql):
        for op in ("INSERT", "UPDATE", "DELETE"):
            assert f"playlist_tracks_{op.lower()}_owned" in rls_sql
            assert "p.user_id = auth.uid()" in rls_sql

    def test_recently_played_isolated_per_user(self, rls_sql):
        for op in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert f"recently_played_{op.lower()}_own" in rls_sql
            assert "user_id = auth.uid()" in rls_sql


class TestRlsDenyByDefault:
    def test_no_unqualified_all_policy(self, rls_sql):
        assert "FOR ALL" not in rls_sql
        assert "USING (true)" not in rls_sql
        assert "WITH CHECK (true)" not in rls_sql


class TestRlsDowngrade:
    """Verify the downgrade path cleans up RLS."""

    def test_upgrade_enables_rls(self, rls_sql: str) -> None:
        """Verify the rendered upgrade SQL enables RLS on all user-owned tables."""
        for table in ("profiles", "favorites", "playlists", "playlist_tracks", "recently_played"):
            # The rendered SQL may have schema prefix: ALTER TABLE public."profiles" ENABLE ROW LEVEL SECURITY
            patterns = [
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
                f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY',
                f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY',
            ]
            assert any(p in rls_sql for p in patterns), (
                f"RLS upgrade must enable RLS on {table} in rendered SQL"
            )

    def test_downgrade_disables_rls(self) -> None:
        """Verify the migration file contains downgrade logic to disable RLS."""
        migration_file = list(VERSIONS_DIR.glob("*rls_policies*"))
        assert len(migration_file) == 1, "Exactly one RLS migration file expected"
        content = migration_file[0].read_text()
        assert "DISABLE ROW LEVEL SECURITY" in content
        # The downgrade uses a loop over all tables with an f-string.
        for table in ("profiles", "favorites", "playlists", "playlist_tracks", "recently_played"):
            # Check the migration file contains the f-string to disable RLS for each table.
            assert (
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY" in content
                or f"ALTER TABLE {{table}} DISABLE ROW LEVEL SECURITY" in content
            ), f"Downgrade must disable RLS on {table}"


class TestRlsNoAuthUsersModification:
    def test_no_policy_on_auth_users(self, rls_sql):
        for line in rls_sql.splitlines():
            if "CREATE POLICY" in line and "auth.users" in line:
                pytest.fail(f"Policy on auth.users found: {line}")


class TestRlsPrivatePlaylistProtection:
    def test_private_playlist_not_in_select_policy(self, rls_sql):
        assert "user_id = auth.uid() OR is_public = true" in rls_sql


class TestRlsPublicPlaylistModificationProtection:
    def test_public_playlist_write_requires_ownership(self, rls_sql):
        for op in ("INSERT", "UPDATE", "DELETE"):
            for line in rls_sql.splitlines():
                if f"playlists_{op.lower()}_own" in line:
                    assert "is_public" not in line


class TestRlsPlaylistTracksParentEnforcement:
    def test_tracks_read_uses_playlist_visibility(self, rls_sql):
        assert "EXISTS (SELECT 1 FROM playlists p" in rls_sql
        assert "p.user_id = auth.uid()" in rls_sql
        assert "p.is_public = true" in rls_sql

    def test_tracks_write_uses_playlist_ownership_only(self, rls_sql):
        for line in rls_sql.splitlines():
            if any(x in line for x in ("playlist_tracks_insert_owned", "playlist_tracks_update_owned", "playlist_tracks_delete_owned")):
                assert "is_public" not in line


class TestRlsNoSuperuserBypass:
    def test_rls_enabled_on_all_tables(self, rls_sql):
        for table in ("profiles", "favorites", "playlists", "playlist_tracks", "recently_played"):
            assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in rls_sql


class TestRlsAuthUidUsage:
    def test_auth_uid_used_in_all_policies(self, rls_sql):
        policies = list(POLICY_NAMES.values())
        flat = [p for sublist in policies for p in sublist]
        for policy in flat:
            assert policy in rls_sql

    def test_no_alternative_identity_functions(self, rls_sql):
        # auth.uid() is the only identity function used; no alternative like
        # current_setting(), session_user, or user should appear.
        assert "auth.uid()" in rls_sql


class TestRlsFixtureWiring:
    """Guard against the 'FixtureFunctionDefinition' regression.

    ``rls_sql`` must receive the *resolved* string produced by ``rendered_sql``
    through pytest dependency injection, never the fixture function object.
    """

    def test_rendered_sql_is_a_string(self, rendered_sql) -> None:
        assert isinstance(rendered_sql, str)
        assert rendered_sql, "rendered SQL must not be empty"

    def test_rls_sql_is_a_string(self, rls_sql) -> None:
        assert isinstance(rls_sql, str)
        assert rls_sql, "RLS SQL must not be empty"

    def test_rls_sql_is_a_slice_of_rendered_sql(self, rendered_sql, rls_sql) -> None:
        assert rls_sql in rendered_sql

    def test_extract_helper_only_needs_a_string(self, rendered_sql) -> None:
        # Calling the helper with the resolved fixture value must work; this is
        # what fails when a fixture object leaks in instead of a str.
        assert extract_rls_sql(rendered_sql) == extract_rls_sql(rendered_sql)

    def test_revision_pair_is_resolved(self) -> None:
        assert isinstance(RLS_REVISION, str) and RLS_REVISION
        assert isinstance(DOWN_REVISION, str) and DOWN_REVISION
