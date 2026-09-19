"""Verification tests for the Alembic migration setup.

These tests run fully offline: they introspect the revision graph and render
the migration with ``alembic upgrade head --sql`` (offline mode never opens a
database connection).  A placeholder PostgreSQL URL is used so the rendered
DDL is Postgres-flavoured; no real credentials are read or required.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

# tests/unit/test_migrations.py -> services/api
API_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_DIR = API_ROOT / "alembic"
VERSIONS_DIR = ALEMBIC_DIR / "versions"
ALEMBIC_INI = API_ROOT / "alembic.ini"

# Placeholder URL: offline rendering only needs the *dialect*, never a
# connection.  Contains no real credentials.
OFFLINE_DATABASE_URL = "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder"

JARUMBA_TABLES = {
    "profiles",
    "favorites",
    "playlists",
    "playlist_tracks",
    "recently_played",
}


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


@pytest.fixture(scope="module")
def rendered_sql() -> str:
    """The SQL emitted by ``alembic upgrade head --sql`` (offline)."""
    result = _run_alembic("upgrade", "head", "--sql")
    assert result.returncode == 0, (
        "offline migration render failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result.stdout


@pytest.fixture(scope="module")
def migration_module():
    """Import the initial schema revision file directly.

    The RLS policies migration (79f3f70e21fc) is a separate revision that
    depends on the initial schema; this fixture targets only the initial
    schema for structural inspection.
    """
    initial = VERSIONS_DIR / "20260916_2003-24333977a264_initial_schema.py"
    assert initial.is_file(), f"initial schema migration not found at {initial}"
    spec = importlib.util.spec_from_file_location("_jarumba_initial_migration", initial)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rls_migration_module():
    """Import the RLS policies revision file directly."""
    rls = VERSIONS_DIR / "20260916_2258-79f3f70e21fc_rls_policies.py"
    assert rls.is_file(), f"RLS migration not found at {rls}"
    spec = importlib.util.spec_from_file_location("_jarumba_rls_migration", rls)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Configuration / file layout
# ---------------------------------------------------------------------------

class TestAlembicLayout:
    def test_alembic_ini_exists(self):
        assert ALEMBIC_INI.is_file()

    def test_env_py_exists(self):
        assert (ALEMBIC_DIR / "env.py").is_file()

    def test_script_directory_exists(self):
        assert VERSIONS_DIR.is_dir()

    def test_stale_rust_migrations_directory_is_gone(self):
        """ADR 0005 supersedes SQLx-style migration dirs at the repo root."""
        assert not (API_ROOT.parent.parent / "migrations").exists()
        assert not (API_ROOT.parent.parent / "supabase" / "migrations").exists()


class TestAlembicConfiguration:
    def test_database_url_is_not_committed(self):
        """alembic.ini must never carry the Supabase connection string."""
        text = ALEMBIC_INI.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("sqlalchemy.url"):
                assert stripped.split("=", 1)[1].strip() == "", (
                    "sqlalchemy.url must be empty in alembic.ini"
                )

    def test_script_location_points_at_alembic_package(self):
        text = ALEMBIC_INI.read_text(encoding="utf-8")
        assert "script_location = alembic" in text

    def test_env_reads_url_from_application_settings(self):
        text = (ALEMBIC_DIR / "env.py").read_text(encoding="utf-8")
        assert "from app.config import get_settings" in text

    def test_env_imports_the_application_metadata(self):
        text = (ALEMBIC_DIR / "env.py").read_text(encoding="utf-8")
        assert "from app.models import Base, auth_users" in text

    def test_include_schemas_is_disabled(self):
        """Reflecting Supabase-owned schemas would emit destructive DROPs."""
        text = (ALEMBIC_DIR / "env.py").read_text(encoding="utf-8")
        assert "include_schemas=False" in text
        # Only inspect executable lines: env.py carries a comment explaining
        # why include_schemas=True would be catastrophic, which must not be
        # mistaken for actual configuration.
        code_lines = [
            ln for ln in text.splitlines() if not ln.strip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "include_schemas=True" not in code

    def test_env_excludes_supabase_owned_tables(self):
        text = (ALEMBIC_DIR / "env.py").read_text(encoding="utf-8")
        assert "def _include_object(" in text
        assert "_include_object" in text.split("run_migrations_offline")[1]
        assert "_include_object" in text.split("run_migrations_online")[1]


# ---------------------------------------------------------------------------
# Revision graph
# ---------------------------------------------------------------------------

class TestRevisionGraph:
    def test_single_head_exists(self):
        result = _run_alembic("heads")
        assert result.returncode == 0, result.stderr
        heads = [ln for ln in result.stdout.splitlines() if "(head)" in ln]
        assert len(heads) == 1, f"expected exactly one head, got {heads}"

    def test_history_lists_the_initial_revision(self):
        result = _run_alembic("history")
        assert result.returncode == 0, result.stderr
        assert "initial" in result.stdout.lower()

    def test_revision_is_the_root_of_the_chain(self, migration_module):
        assert migration_module.revision
        assert migration_module.down_revision is None

    def test_revision_declares_branch_and_dependency_slots(self, migration_module):
        assert migration_module.branch_labels is None
        assert migration_module.depends_on is None

    def test_revision_defines_both_directions(self, migration_module):
        assert callable(migration_module.upgrade)
        assert callable(migration_module.downgrade)


# ---------------------------------------------------------------------------
# Rendered schema matches the intended PostgreSQL schema
# ---------------------------------------------------------------------------

class TestRenderedSchema:
    def test_creates_exactly_the_jarumba_tables(self, rendered_sql):
        import re

        created = set(re.findall(r"CREATE TABLE (\w+)", rendered_sql))
        assert created == JARUMBA_TABLES | {"alembic_version"}

    def test_upgrade_contains_no_destructive_statements(self, rendered_sql):
        """The upgrade chain must never destroy data or schema objects.

        ``TRUNCATE`` needs care: the RLS table-privileges migration legitimately
        emits ``REVOKE TRUNCATE, REFERENCES, TRIGGER, MAINTAIN ON TABLE ... FROM
        anon, authenticated`` as part of Supabase hardening.  That is a
        privilege *revocation*, not a data-destroying statement, so only genuine
        ``TRUNCATE`` statements count as destructive here.
        """
        upper = rendered_sql.upper()
        for destructive in ("DROP TABLE", "DROP COLUMN", "DROP SCHEMA"):
            assert destructive not in upper, f"upgrade must not emit {destructive}"
        for line in rendered_sql.splitlines():
            statement = line.strip().upper()
            # Skip privilege lists such as "REVOKE TRUNCATE, ... FROM role;".
            if statement.startswith("REVOKE") or statement.startswith("--"):
                continue
            assert "TRUNCATE" not in statement, (
                f"upgrade must not emit TRUNCATE: {line.strip()}"
            )

    def test_supabase_auth_users_is_referenced_but_never_created(self, rendered_sql):
        # The FK target must appear...
        assert "auth.users" in rendered_sql
        # ...but we must never create, alter, or drop the Supabase-owned table.
        assert "CREATE TABLE auth.users" not in rendered_sql
        assert "CREATE TABLE auth_users" not in rendered_sql

    def test_profiles_id_is_uuid_primary_key_with_cascading_fk(self, rendered_sql):
        import re

        block = re.search(
            r"CREATE TABLE profiles \((.*?)\);", rendered_sql, re.DOTALL
        ).group(1)
        assert "id UUID NOT NULL" in block
        assert "PRIMARY KEY (id)" in block
        assert "FOREIGN KEY(id) REFERENCES auth.users (id) ON DELETE CASCADE" in block

    def test_favorites_prevents_duplicate_provider_tracks(self, rendered_sql):
        assert (
            "CONSTRAINT uk_favorites_user_provider_track UNIQUE "
            "(user_id, provider, provider_track_id)" in rendered_sql
        )

    def test_playlist_tracks_position_is_deferrable_and_ordered(self, rendered_sql):
        assert (
            "CONSTRAINT uk_playlist_tracks_playlist_position UNIQUE "
            "(playlist_id, position) DEFERRABLE INITIALLY DEFERRED" in rendered_sql
        )
        assert "CONSTRAINT ck_playlist_tracks_position_non_negative CHECK (position >= 0)" in rendered_sql

    def test_playlist_tracks_prevents_duplicate_tracks(self, rendered_sql):
        assert (
            "CONSTRAINT uk_playlist_tracks_playlist_track UNIQUE "
            "(playlist_id, provider, provider_track_id)" in rendered_sql
        )

    def test_cascade_from_profiles_to_owned_rows(self, rendered_sql):
        import re

        # Each table's own CREATE TABLE block must carry its own cascading
        # FK: a single occurrence of the generic string anywhere in the
        # script must NOT satisfy all three (the previous loop-based
        # assertion could pass on one match alone).
        def block(table: str) -> str:
            match = re.search(
                rf"CREATE TABLE {table} \((.*?)\);", rendered_sql, re.DOTALL
            )
            assert match, f"CREATE TABLE {table} not found in rendered SQL"
            return match.group(1)

        for table in ("favorites", "playlists", "recently_played"):
            table_block = block(table)
            assert (
                "FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE"
                in table_block
            ), f"{table} must cascade from profiles"
        playlist_tracks_block = block("playlist_tracks")
        assert (
            "FOREIGN KEY(playlist_id) REFERENCES playlists (id) ON DELETE CASCADE"
            in playlist_tracks_block
        ), "playlist_tracks must cascade from playlists"

    def test_recently_played_has_no_unique_track_constraint(self, rendered_sql):
        """Play history is temporal, so repeated plays must be allowed."""
        assert "CREATE TABLE recently_played" in rendered_sql
        assert "uk_recently_played" not in rendered_sql

    def test_uuid_server_defaults_are_used(self, rendered_sql):
        assert rendered_sql.count("DEFAULT gen_random_uuid()") >= 4

    def test_indexes_are_created(self, rendered_sql):
        for index in (
            "idx_profiles_display_name",
            "idx_favorites_user_created_at",
            "idx_playlists_user_created_at",
            "idx_recently_played_user_played_at",
            "idx_recently_played_user_provider_track",
        ):
            assert f"CREATE INDEX {index}" in rendered_sql

    def test_no_audio_payload_columns_are_stored(self, rendered_sql):
        for column in ("audio_url", "stream_url", "audio", "file_path", "audio_data"):
            assert column not in rendered_sql

    def test_license_metadata_is_preserved(self, rendered_sql):
        assert rendered_sql.count("license_url") >= 3
        assert rendered_sql.count("license_name") >= 3




