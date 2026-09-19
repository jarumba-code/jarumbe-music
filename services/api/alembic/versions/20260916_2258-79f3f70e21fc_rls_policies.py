"""rls_policies

Revision ID: 79f3f70e21fc
Revises: 24333977a264
Create Date: 2026-09-16 22:58:39.508621+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "79f3f70e21fc"
down_revision: Union[str, None] = "24333977a264"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable RLS and create policies on all user-owned tables."""
    # --- profiles ---
    op.execute(sa.text("ALTER TABLE profiles ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY profiles_select_own ON profiles "
        "FOR SELECT USING (id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY profiles_insert_own ON profiles "
        "FOR INSERT WITH CHECK (id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY profiles_update_own ON profiles "
        "FOR UPDATE USING (id = auth.uid()) "
        "WITH CHECK (id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY profiles_delete_own ON profiles "
        "FOR DELETE USING (id = auth.uid())"
    ))

    # --- favorites ---
    op.execute(sa.text("ALTER TABLE favorites ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY favorites_select_own ON favorites "
        "FOR SELECT USING (user_id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY favorites_insert_own ON favorites "
        "FOR INSERT WITH CHECK (user_id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY favorites_update_own ON favorites "
        "FOR UPDATE USING (user_id = auth.uid()) "
        "WITH CHECK (user_id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY favorites_delete_own ON favorites "
        "FOR DELETE USING (user_id = auth.uid())"
    ))

    # --- playlists ---
    op.execute(sa.text("ALTER TABLE playlists ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY playlists_select_accessible ON playlists "
        "FOR SELECT USING (user_id = auth.uid() OR is_public = true)"
    ))
    op.execute(sa.text(
        "CREATE POLICY playlists_insert_own ON playlists "
        "FOR INSERT WITH CHECK (user_id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY playlists_update_own ON playlists "
        "FOR UPDATE USING (user_id = auth.uid()) "
        "WITH CHECK (user_id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY playlists_delete_own ON playlists "
        "FOR DELETE USING (user_id = auth.uid())"
    ))

    # --- playlist_tracks ---
    op.execute(sa.text("ALTER TABLE playlist_tracks ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY playlist_tracks_select_accessible ON playlist_tracks "
        "FOR SELECT USING ("
        "EXISTS (SELECT 1 FROM playlists p "
        "WHERE p.id = playlist_tracks.playlist_id "
        "AND (p.user_id = auth.uid() OR p.is_public = true))"
        ")"
    ))
    op.execute(sa.text(
        "CREATE POLICY playlist_tracks_insert_owned ON playlist_tracks "
        "FOR INSERT WITH CHECK ("
        "EXISTS (SELECT 1 FROM playlists p "
        "WHERE p.id = playlist_tracks.playlist_id "
        "AND p.user_id = auth.uid())"
        ")"
    ))
    op.execute(sa.text(
        "CREATE POLICY playlist_tracks_update_owned ON playlist_tracks "
        "FOR UPDATE USING ("
        "EXISTS (SELECT 1 FROM playlists p "
        "WHERE p.id = playlist_tracks.playlist_id "
        "AND p.user_id = auth.uid())"
        ") WITH CHECK ("
        "EXISTS (SELECT 1 FROM playlists p "
        "WHERE p.id = playlist_tracks.playlist_id "
        "AND p.user_id = auth.uid())"
        ")"
    ))
    op.execute(sa.text(
        "CREATE POLICY playlist_tracks_delete_owned ON playlist_tracks "
        "FOR DELETE USING ("
        "EXISTS (SELECT 1 FROM playlists p "
        "WHERE p.id = playlist_tracks.playlist_id "
        "AND p.user_id = auth.uid())"
        ")"
    ))

    # --- recently_played ---
    op.execute(sa.text("ALTER TABLE recently_played ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY recently_played_select_own ON recently_played "
        "FOR SELECT USING (user_id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY recently_played_insert_own ON recently_played "
        "FOR INSERT WITH CHECK (user_id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY recently_played_update_own ON recently_played "
        "FOR UPDATE USING (user_id = auth.uid()) "
        "WITH CHECK (user_id = auth.uid())"
    ))
    op.execute(sa.text(
        "CREATE POLICY recently_played_delete_own ON recently_played "
        "FOR DELETE USING (user_id = auth.uid())"
    ))


def downgrade() -> None:
    """Drop all RLS policies and disable RLS on all user-owned tables."""
    for table in ("profiles", "favorites", "playlists", "playlist_tracks", "recently_played"):
        op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
