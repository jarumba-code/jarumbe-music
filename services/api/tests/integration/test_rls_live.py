"""Live RLS enforcement verification against a real Supabase PostgreSQL database.

Unit tests in ``tests/unit/test_rls.py`` prove the *policies are written
correctly*.  This module proves the *database actually enforces them*: every
assertion below is a real RLS decision made by PostgreSQL on the development
Supabase instance.

Opt-in only
-----------
These tests need a live database, so they are **skipped** unless both

* ``JARUMBA_RUN_LIVE_RLS=1`` is set, and
* ``JARUMBA_LIVE_DATABASE_URL`` points at the PostgreSQL database that a
  human has **explicitly** designated for live verification.

There is **no fallback** to ``DATABASE_URL``.  ``DATABASE_URL`` is the normal
application database configuration and must never be inferred as the live-test
target: the test suite can only ever target the database named by
``JARUMBA_LIVE_DATABASE_URL``, which is set deliberately, by hand, for a
controlled private verification run.

That keeps the default ``pytest`` run hermetic while still allowing a genuine
end-to-end security check.

How impersonation works
-----------------------
Supabase (PostgREST) serves user requests as the ``authenticated`` role with the
verified JWT claims placed in the ``request.jwt.claims`` setting.  ``auth.uid()``
reads ``sub`` from there.  This module reproduces exactly that:

    SET LOCAL ROLE authenticated;
    SELECT set_config('request.jwt.claims', '{"sub": "<uuid>", ...}', true);

so ``auth.uid()`` resolves to the impersonated user and the policies in
``79f3f70e21fc`` decide the outcome.

Nothing is persisted
--------------------
Each test runs inside a single transaction that is rolled back in teardown, so
no test identities or rows survive the run.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
import sqlalchemy as sa  # noqa: E402

API_ROOT = Path(__file__).resolve().parents[2]

LIVE_FLAG = "JARUMBA_RUN_LIVE_RLS"

JARUMBA_TABLES = (
    "profiles",
    "favorites",
    "playlists",
    "playlist_tracks",
    "recently_played",
)


def _live_database_url() -> str | None:
    """Return the explicitly configured live URL, if any (never logged).

    Deliberately does **not** fall back to ``DATABASE_URL``: that variable is
    the normal application database configuration, and the live-test suite
    must never infer its target from it.  Only an explicit
    ``JARUMBA_LIVE_DATABASE_URL`` — set by a human for a controlled
    verification run — can point these tests at a database.
    """
    url = os.environ.get("JARUMBA_LIVE_DATABASE_URL")
    return url if url else None


pytestmark = pytest.mark.skipif(
    os.environ.get(LIVE_FLAG) != "1" or not _live_database_url(),
    reason=(
        f"live RLS verification is opt-in: set {LIVE_FLAG}=1 and "
        "JARUMBA_LIVE_DATABASE_URL (explicitly; DATABASE_URL is never used "
        "as a fallback) to a PostgreSQL database to run it"
    ),
)


# ---------------------------------------------------------------------------
# Identities and fixtures
#
# Random UUIDs per run: the assertions can never accidentally pass because a
# pre-existing row happened to match.
# ---------------------------------------------------------------------------

USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())

PROFILE_A = USER_A
PROFILE_B = USER_B

FAV_A = str(uuid.uuid4())
FAV_B = str(uuid.uuid4())

PLAYLIST_A_PRIVATE = str(uuid.uuid4())
PLAYLIST_A_PUBLIC = str(uuid.uuid4())
PLAYLIST_B_PRIVATE = str(uuid.uuid4())
PLAYLIST_B_PUBLIC = str(uuid.uuid4())

TRACK_A_PRIVATE = str(uuid.uuid4())
TRACK_A_PUBLIC = str(uuid.uuid4())
TRACK_B_PRIVATE = str(uuid.uuid4())
TRACK_B_PUBLIC = str(uuid.uuid4())

PLAY_A = str(uuid.uuid4())
PLAY_B = str(uuid.uuid4())


@pytest.fixture(scope="module")
def live_engine():
    """Engine bound to the live development database."""
    url = _live_database_url()
    assert url, "live database URL is not configured"
    engine = sa.create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as probe:
            probe.execute(sa.text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"live database is unreachable: {type(exc).__name__}")
    yield engine
    engine.dispose()


def impersonate(conn, user_id: str) -> None:
    """Switch the session to ``authenticated`` acting as ``user_id``."""
    conn.execute(sa.text("SET LOCAL ROLE authenticated"))
    conn.execute(
        sa.text("SELECT set_config('request.jwt.claims', :claims, true)"),
        {"claims": '{"sub": "%s", "role": "authenticated"}' % user_id},
    )


def become_anon(conn) -> None:
    """Switch the session to the unauthenticated Supabase role."""
    conn.execute(sa.text("SET LOCAL ROLE anon"))
    conn.execute(
        sa.text("SELECT set_config('request.jwt.claims', :claims, true)"),
        {"claims": "{}"},
    )


def become_owner(conn) -> None:
    """Return to the connecting (table-owner) role used for fixture setup."""
    conn.execute(sa.text("RESET ROLE"))


def seed(conn) -> None:
    """Insert the fixture rows as the owning role."""
    become_owner(conn)
    for uid in (USER_A, USER_B):
        conn.execute(
            sa.text("INSERT INTO auth.users (id) VALUES (:id) ON CONFLICT DO NOTHING"),
            {"id": uid},
        )
    for uid in (USER_A, USER_B):
        conn.execute(
            sa.text(
                "INSERT INTO profiles (id, display_name) VALUES (:id, :name) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": uid, "name": f"user-{uid[:8]}"},
        )
    for fav_id, uid in ((FAV_A, USER_A), (FAV_B, USER_B)):
        conn.execute(
            sa.text(
                "INSERT INTO favorites "
                "(id, user_id, provider, provider_track_id, title, artist) "
                "VALUES (:id, :uid, 'jamendo', :track, 'seed', :artist)"
            ),
            {"id": fav_id, "uid": uid, "track": f"fav-{fav_id[:8]}", "artist": "seed"},
        )
    playlists = (
        (PLAYLIST_A_PRIVATE, USER_A, False),
        (PLAYLIST_A_PUBLIC, USER_A, True),
        (PLAYLIST_B_PRIVATE, USER_B, False),
        (PLAYLIST_B_PUBLIC, USER_B, True),
    )
    for pl_id, uid, is_public in playlists:
        conn.execute(
            sa.text(
                "INSERT INTO playlists (id, user_id, name, is_public) "
                "VALUES (:id, :uid, :name, :public)"
            ),
            {"id": pl_id, "uid": uid, "name": f"pl-{pl_id[:8]}", "public": is_public},
        )
    tracks = (
        (TRACK_A_PRIVATE, PLAYLIST_A_PRIVATE),
        (TRACK_A_PUBLIC, PLAYLIST_A_PUBLIC),
        (TRACK_B_PRIVATE, PLAYLIST_B_PRIVATE),
        (TRACK_B_PUBLIC, PLAYLIST_B_PUBLIC),
    )
    for track_id, pl_id in tracks:
        conn.execute(
            sa.text(
                "INSERT INTO playlist_tracks "
                "(id, playlist_id, position, provider, provider_track_id, title, artist) "
                "VALUES (:id, :pl, 0, 'jamendo', :track, 'seed', :artist)"
            ),
            {"id": track_id, "pl": pl_id, "track": f"track-{track_id[:8]}", "artist": "seed"},
        )
    for play_id, uid in ((PLAY_A, USER_A), (PLAY_B, USER_B)):
        conn.execute(
            sa.text(
                "INSERT INTO recently_played "
                "(id, user_id, provider, provider_track_id, title, artist) "
                "VALUES (:id, :uid, 'jamendo', :track, 'seed', :artist)"
            ),
            {"id": play_id, "uid": uid, "track": f"play-{play_id[:8]}", "artist": "seed"},
        )


@pytest.fixture()
def conn(live_engine):
    """A transaction with fixtures seeded; rolled back in teardown."""
    connection = live_engine.connect()
    transaction = connection.begin()
    try:
        seed(connection)
        yield connection
    finally:
        transaction.rollback()
        connection.close()


def scalar(conn, sql: str, **params):
    """Return the first column of the first row."""
    return conn.execute(sa.text(sql), params).scalar()


def count(conn, sql: str, **params) -> int:
    """Return a row count (0 when nothing is visible)."""
    value = conn.execute(sa.text(sql), params).scalar()
    return int(value or 0)


def write_succeeds(conn, sql: str, **params) -> bool:
    """Run a DML statement in a savepoint; ``True`` when PostgreSQL allowed it."""
    try:
        with conn.begin_nested():
            conn.execute(sa.text(sql), params)
        return True
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "row-level security" in message or "permission denied" in message:
            return False
        raise
def affected(conn, sql: str, **params) -> int:
    """Run DML and return the number of rows PostgreSQL actually touched.

    An ``UPDATE``/``DELETE`` whose ``USING`` clause hides the target row is not
    an error in PostgreSQL: it simply matches zero rows.  Row count is therefore
    the honest signal for "RLS filtered this out".
    """
    result = conn.execute(sa.text(sql), params)
    return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# profiles — identity and self-service only
# ---------------------------------------------------------------------------

class TestProfilesIsolation:
    def test_owner_reads_own_profile(self, conn):
        impersonate(conn, USER_A)
        assert count(conn, "SELECT 1 FROM profiles WHERE id = :id", id=PROFILE_A) == 1

    def test_cannot_read_another_users_profile(self, conn):
        impersonate(conn, USER_A)
        assert count(conn, "SELECT 1 FROM profiles WHERE id = :id", id=PROFILE_B) == 0

    def test_cannot_update_another_users_profile(self, conn):
        impersonate(conn, USER_A)
        changed = affected(
            conn,
            "UPDATE profiles SET display_name = 'hijacked' WHERE id = :id",
            id=PROFILE_B,
        )
        assert changed == 0, "RLS must hide other users' profiles from UPDATE"
        become_owner(conn)
        assert scalar(
            conn, "SELECT display_name FROM profiles WHERE id = :id", id=PROFILE_B
        ) != "hijacked"

    def test_can_update_own_profile(self, conn):
        impersonate(conn, USER_A)
        changed = affected(
            conn,
            "UPDATE profiles SET display_name = 'renamed' WHERE id = :id",
            id=PROFILE_A,
        )
        assert changed == 1
        assert scalar(
            conn, "SELECT display_name FROM profiles WHERE id = :id", id=PROFILE_A
        ) == "renamed"

    def test_cannot_delete_another_users_profile(self, conn):
        impersonate(conn, USER_A)
        assert affected(conn, "DELETE FROM profiles WHERE id = :id", id=PROFILE_B) == 0
        become_owner(conn)
        assert count(conn, "SELECT 1 FROM profiles WHERE id = :id", id=PROFILE_B) == 1

    def test_cannot_insert_a_profile_for_another_user(self, conn):
        impersonate(conn, USER_A)
        ok = write_succeeds(
            conn,
            "INSERT INTO profiles (id, display_name) VALUES (:id, 'impostor')",
            id=str(uuid.uuid4()),
        )
        assert not ok, "WITH CHECK must reject a profile whose id is not auth.uid()"

    def test_can_insert_own_profile(self, conn):
        """A brand-new authenticated user can initialise their own profile."""
        new_user = str(uuid.uuid4())
        become_owner(conn)
        conn.execute(
            sa.text("INSERT INTO auth.users (id) VALUES (:id) ON CONFLICT DO NOTHING"),
            {"id": new_user},
        )
        impersonate(conn, new_user)
        ok = write_succeeds(
            conn,
            "INSERT INTO profiles (id, display_name) VALUES (:id, 'fresh')",
            id=new_user,
        )
        assert ok

# ---------------------------------------------------------------------------
# favorites — strictly per user
# ---------------------------------------------------------------------------

class TestFavoritesIsolation:
    def test_owner_reads_own_favorite(self, conn):
        impersonate(conn, USER_A)
        assert count(conn, "SELECT 1 FROM favorites WHERE id = :id", id=FAV_A) == 1

    def test_cannot_read_another_users_favorite(self, conn):
        impersonate(conn, USER_A)
        assert count(conn, "SELECT 1 FROM favorites WHERE id = :id", id=FAV_B) == 0

    def test_can_insert_own_favorite(self, conn):
        impersonate(conn, USER_A)
        ok = write_succeeds(
            conn,
            "INSERT INTO favorites (id, user_id, provider, provider_track_id, title, artist) "
            "VALUES (:id, :uid, 'jamendo', 't-own', 'mine', 'seed')",
            id=str(uuid.uuid4()),
            uid=USER_A,
        )
        assert ok

    def test_cannot_insert_a_favorite_for_another_user(self, conn):
        impersonate(conn, USER_A)
        ok = write_succeeds(
            conn,
            "INSERT INTO favorites (id, user_id, provider, provider_track_id, title, artist) "
            "VALUES (:id, :uid, 'jamendo', 't-theirs', 'theirs', 'seed')",
            id=str(uuid.uuid4()),
            uid=USER_B,
        )
        assert not ok, "WITH CHECK must reject user_id != auth.uid()"

    def test_cannot_update_another_users_favorite(self, conn):
        impersonate(conn, USER_A)
        assert (
            affected(
                conn, "UPDATE favorites SET title = 'hijacked' WHERE id = :id", id=FAV_B
            )
            == 0
        )
        become_owner(conn)
        assert scalar(conn, "SELECT title FROM favorites WHERE id = :id", id=FAV_B) != "hijacked"

    def test_cannot_delete_another_users_favorite(self, conn):
        impersonate(conn, USER_A)
        assert affected(conn, "DELETE FROM favorites WHERE id = :id", id=FAV_B) == 0
        become_owner(conn)
        assert count(conn, "SELECT 1 FROM favorites WHERE id = :id", id=FAV_B) == 1

    def test_can_delete_own_favorite(self, conn):
        impersonate(conn, USER_A)
        assert affected(conn, "DELETE FROM favorites WHERE id = :id", id=FAV_A) == 1

# ---------------------------------------------------------------------------
# playlists — owner + public visibility
# ---------------------------------------------------------------------------

class TestPlaylistsIsolation:
    def test_owner_reads_own_private_playlist(self, conn):
        impersonate(conn, USER_A)
        assert count(conn, "SELECT 1 FROM playlists WHERE id = :id", id=PLAYLIST_A_PRIVATE) == 1

    def test_owner_can_insert_own_playlist(self, conn):
        impersonate(conn, USER_A)
        ok = write_succeeds(
            conn,
            "INSERT INTO playlists (id, user_id, name, is_public) "
            "VALUES (:id, :uid, 'mine', false)",
            id=str(uuid.uuid4()),
            uid=USER_A,
        )
        assert ok

    def test_owner_can_update_own_playlist(self, conn):
        impersonate(conn, USER_A)
        changed = affected(
            conn,
            "UPDATE playlists SET name = 'renamed' WHERE id = :id",
            id=PLAYLIST_A_PRIVATE,
        )
        assert changed == 1
        assert scalar(
            conn, "SELECT name FROM playlists WHERE id = :id", id=PLAYLIST_A_PRIVATE
        ) == "renamed"

    def test_owner_can_delete_own_playlist(self, conn):
        impersonate(conn, USER_A)
        assert affected(conn, "DELETE FROM playlists WHERE id = :id", id=PLAYLIST_A_PUBLIC) == 1
        become_owner(conn)
        assert count(conn, "SELECT 1 FROM playlists WHERE id = :id", id=PLAYLIST_A_PUBLIC) == 0

    def test_cannot_read_others_private_playlist(self, conn):
        impersonate(conn, USER_A)
        assert count(conn, "SELECT 1 FROM playlists WHERE id = :id", id=PLAYLIST_B_PRIVATE) == 0

    def test_cannot_update_others_playlist(self, conn):
        impersonate(conn, USER_A)
        changed = affected(
            conn,
            "UPDATE playlists SET name = 'hijacked' WHERE id = :id",
            id=PLAYLIST_B_PRIVATE,
        )
        assert changed == 0
        become_owner(conn)
        assert scalar(
            conn, "SELECT name FROM playlists WHERE id = :id", id=PLAYLIST_B_PRIVATE
        ) != "hijacked"

    def test_cannot_delete_others_playlist(self, conn):
        impersonate(conn, USER_A)
        assert affected(conn, "DELETE FROM playlists WHERE id = :id", id=PLAYLIST_B_PRIVATE) == 0
        become_owner(conn)
        assert count(conn, "SELECT 1 FROM playlists WHERE id = :id", id=PLAYLIST_B_PRIVATE) == 1


class TestPublicPlaylistVisibility:
    def test_public_playlist_readable_by_non_owner(self, conn):
        impersonate(conn, USER_A)
        assert count(conn, "SELECT 1 FROM playlists WHERE id = :id", id=PLAYLIST_B_PUBLIC) == 1

    def test_public_visibility_does_not_grant_update(self, conn):
        impersonate(conn, USER_A)
        changed = affected(
            conn,
            "UPDATE playlists SET name = 'hijacked' WHERE id = :id",
            id=PLAYLIST_B_PUBLIC,
        )
        assert changed == 0
        become_owner(conn)
        assert scalar(
            conn, "SELECT name FROM playlists WHERE id = :id", id=PLAYLIST_B_PUBLIC
        ) != "hijacked"

    def test_public_visibility_does_not_grant_delete(self, conn):
        impersonate(conn, USER_A)
        assert affected(conn, "DELETE FROM playlists WHERE id = :id", id=PLAYLIST_B_PUBLIC) == 0
        become_owner(conn)
        assert count(conn, "SELECT 1 FROM playlists WHERE id = :id", id=PLAYLIST_B_PUBLIC) == 1


# ---------------------------------------------------------------------------
# playlist_tracks — ownership flows through the parent playlist
# ---------------------------------------------------------------------------

def _insert_track_sql() -> str:
    return (
        "INSERT INTO playlist_tracks "
        "(id, playlist_id, position, provider, provider_track_id, title, artist) "
        "VALUES (:id, :pid, 0, 'jamendo', 't-new', 'seed', 'seed')"
    )


class TestPlaylistTracksIsolation:
    def test_owner_reads_own_playlist_tracks(self, conn):
        impersonate(conn, USER_A)
        assert count(
            conn, "SELECT 1 FROM playlist_tracks WHERE playlist_id = :pid", pid=PLAYLIST_A_PRIVATE
        ) == 1

    def test_non_owner_cannot_read_private_playlist_tracks(self, conn):
        impersonate(conn, USER_A)
        assert count(
            conn, "SELECT 1 FROM playlist_tracks WHERE playlist_id = :pid", pid=PLAYLIST_B_PRIVATE
        ) == 0

    def test_owner_can_insert_track(self, conn):
        impersonate(conn, USER_A)
        ok = write_succeeds(
            conn, _insert_track_sql(), id=str(uuid.uuid4()), pid=PLAYLIST_A_PRIVATE
        )
        assert ok

    def test_owner_can_reorder_track(self, conn):
        impersonate(conn, USER_A)
        changed = affected(
            conn,
            "UPDATE playlist_tracks SET position = 5 WHERE playlist_id = :pid",
            pid=PLAYLIST_A_PRIVATE,
        )
        assert changed == 1
        assert scalar(
            conn,
            "SELECT position FROM playlist_tracks WHERE playlist_id = :pid",
            pid=PLAYLIST_A_PRIVATE,
        ) == 5

    def test_owner_can_delete_track(self, conn):
        impersonate(conn, USER_A)
        assert affected(
            conn, "DELETE FROM playlist_tracks WHERE playlist_id = :pid", pid=PLAYLIST_A_PRIVATE
        ) == 1
        become_owner(conn)
        assert count(
            conn, "SELECT 1 FROM playlist_tracks WHERE playlist_id = :pid", pid=PLAYLIST_A_PRIVATE
        ) == 0

    def test_non_owner_cannot_update_others_tracks(self, conn):
        impersonate(conn, USER_A)
        assert affected(
            conn,
            "UPDATE playlist_tracks SET position = 9 WHERE playlist_id = :pid",
            pid=PLAYLIST_B_PRIVATE,
        ) == 0

    def test_public_playlist_does_not_grant_track_insert(self, conn):
        """Visibility of a playlist must never allow adding tracks to it."""
        impersonate(conn, USER_A)
        ok = write_succeeds(
            conn, _insert_track_sql(), id=str(uuid.uuid4()), pid=PLAYLIST_B_PUBLIC
        )
        assert not ok, "insert policy must require owning the parent playlist"

    def test_public_playlist_does_not_grant_track_update(self, conn):
        impersonate(conn, USER_A)
        assert affected(
            conn,
            "UPDATE playlist_tracks SET position = 9 WHERE playlist_id = :pid",
            pid=PLAYLIST_B_PUBLIC,
        ) == 0


# ---------------------------------------------------------------------------
# recently_played — strictly per user
# ---------------------------------------------------------------------------

class TestRecentlyPlayedIsolation:
    def test_owner_inserts_own_history(self, conn):
        impersonate(conn, USER_A)
        ok = write_succeeds(
            conn,
            "INSERT INTO recently_played "
            "(id, user_id, provider, provider_track_id, title, artist) "
            "VALUES (:id, :uid, 'jamendo', 'hist-new', 'seed', 'seed')",
            id=str(uuid.uuid4()),
            uid=USER_A,
        )
        assert ok

    def test_owner_reads_own_history(self, conn):
        impersonate(conn, USER_A)
        assert count(conn, "SELECT 1 FROM recently_played WHERE id = :id", id=PLAY_A) == 1

    def test_owner_can_delete_own_history(self, conn):
        impersonate(conn, USER_A)
        assert affected(conn, "DELETE FROM recently_played WHERE id = :id", id=PLAY_A) == 1
        become_owner(conn)
        assert count(conn, "SELECT 1 FROM recently_played WHERE id = :id", id=PLAY_A) == 0

    def test_cannot_read_others_history(self, conn):
        impersonate(conn, USER_A)
        assert count(conn, "SELECT 1 FROM recently_played WHERE id = :id", id=PLAY_B) == 0

    def test_cannot_insert_history_for_another_user(self, conn):
        impersonate(conn, USER_A)
        ok = write_succeeds(
            conn,
            "INSERT INTO recently_played "
            "(id, user_id, provider, provider_track_id, title, artist) "
            "VALUES (:id, :uid, 'jamendo', 'hist-b', 'seed', 'seed')",
            id=str(uuid.uuid4()),
            uid=USER_B,
        )
        assert not ok, "WITH CHECK must reject user_id != auth.uid()"

    def test_cannot_update_others_history(self, conn):
        impersonate(conn, USER_A)
        changed = affected(
            conn,
            "UPDATE recently_played SET title = 'hijacked' WHERE id = :id",
            id=PLAY_B,
        )
        assert changed == 0
        become_owner(conn)
        assert scalar(
            conn, "SELECT title FROM recently_played WHERE id = :id", id=PLAY_B
        ) != "hijacked"

    def test_cannot_delete_others_history(self, conn):
        impersonate(conn, USER_A)
        assert affected(conn, "DELETE FROM recently_played WHERE id = :id", id=PLAY_B) == 0
        become_owner(conn)
        assert count(conn, "SELECT 1 FROM recently_played WHERE id = :id", id=PLAY_B) == 1


# ---------------------------------------------------------------------------
# anon — unauthenticated callers get nothing
# ---------------------------------------------------------------------------

def read_succeeds(conn, sql: str, **params) -> bool:
    """Run a read in a savepoint; ``True`` when PostgreSQL allowed it.

    ``anon`` holds no table privileges at all, so a denied read surfaces as a
    permission error (SQLSTATE 42501), not as an empty result.
    """
    try:
        with conn.begin_nested():
            conn.execute(sa.text(sql), params)
        return True
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "row-level security" in message or "permission denied" in message:
            return False
        raise


class TestAnonDenied:
    def test_anon_cannot_read_profiles(self, conn):
        become_anon(conn)
        assert not read_succeeds(conn, "SELECT 1 FROM profiles LIMIT 1")

    def test_anon_cannot_read_favorites(self, conn):
        become_anon(conn)
        assert not read_succeeds(conn, "SELECT 1 FROM favorites LIMIT 1")

    def test_anon_cannot_read_playlists(self, conn):
        """Not even public playlists: anon holds no table privilege at all."""
        become_anon(conn)
        assert not read_succeeds(conn, "SELECT 1 FROM playlists LIMIT 1")

    def test_anon_cannot_read_playlist_tracks(self, conn):
        become_anon(conn)
        assert not read_succeeds(conn, "SELECT 1 FROM playlist_tracks LIMIT 1")

    def test_anon_cannot_read_recently_played(self, conn):
        become_anon(conn)
        assert not read_succeeds(conn, "SELECT 1 FROM recently_played LIMIT 1")

    def test_anon_cannot_insert_profile(self, conn):
        become_anon(conn)
        ok = write_succeeds(
            conn,
            "INSERT INTO profiles (id, display_name) VALUES (:id, 'anon')",
            id=str(uuid.uuid4()),
        )
        assert not ok

    def test_anon_cannot_insert_favorite(self, conn):
        become_anon(conn)
        ok = write_succeeds(
            conn,
            "INSERT INTO favorites (id, user_id, provider, provider_track_id, title, artist) "
            "VALUES (:id, :uid, 'jamendo', 'anon', 'anon', 'anon')",
            id=str(uuid.uuid4()),
            uid=str(uuid.uuid4()),
        )
        assert not ok

    def test_anon_cannot_insert_playlist(self, conn):
        become_anon(conn)
        ok = write_succeeds(
            conn,
            "INSERT INTO playlists (id, user_id, name, is_public) "
            "VALUES (:id, :uid, 'anon', true)",
            id=str(uuid.uuid4()),
            uid=str(uuid.uuid4()),
        )
        assert not ok

    def test_anon_cannot_insert_history(self, conn):
        become_anon(conn)
        ok = write_succeeds(
            conn,
            "INSERT INTO recently_played "
            "(id, user_id, provider, provider_track_id, title, artist) "
            "VALUES (:id, :uid, 'jamendo', 'anon', 'anon', 'anon')",
            id=str(uuid.uuid4()),
            uid=str(uuid.uuid4()),
        )
        assert not ok

    def test_anon_cannot_modify_or_delete_rows(self, conn):
        become_anon(conn)
        assert not write_succeeds(
            conn, "UPDATE profiles SET display_name = 'anon' WHERE id = :id", id=PROFILE_A
        )
        assert not write_succeeds(
            conn, "DELETE FROM favorites WHERE id = :id", id=FAV_A
        )

    def test_anon_cannot_execute_admin_helper(self, conn):
        """The SECURITY DEFINER guard function must reject anon at call time."""
        become_anon(conn)
        assert not read_succeeds(conn, "SELECT jarumba_admin.rls_auto_enable()")

    def test_admin_helper_privileges_in_database_state(self, conn):
        """Verify the real privilege state behind the security-advisor finding."""
        become_owner(conn)
        assert scalar(
            conn,
            "SELECT has_function_privilege('anon', "
            "'jarumba_admin.rls_auto_enable()', 'EXECUTE')",
        ) is False
        assert scalar(
            conn,
            "SELECT has_function_privilege('authenticated', "
            "'jarumba_admin.rls_auto_enable()', 'EXECUTE')",
        ) is False
        # And it no longer lives in the API-exposed 'public' schema at all.
        assert scalar(
            conn, "SELECT to_regprocedure('public.rls_auto_enable()') IS NULL"
        ) is True
