"""rls_table_privileges

Revision ID: 7d5ff3e7ecf8
Revises: 79f3f70e21fc
Create Date: 2026-09-17 09:11:07.963436+00:00

Grant table privileges to the Supabase API roles.

RLS policies filter *rows*; they are evaluated only after PostgreSQL has
already decided whether a role may touch the table at all.  Supabase ships a
hardened default where ``anon``/``authenticated``/``service_role`` hold only
``Dxtm`` (TRUNCATE/REFERENCES/TRIGGER/MAINTAIN) and **no** DML.  That makes
every policy in ``79f3f70e21fc`` unreachable - the owner of a row could not
even read it, and an unauthenticated caller could still ``TRUNCATE`` it.

This migration closes that gap:

* ``anon``          - no table privileges at all (deny-by-default for
                      unauthenticated callers, including PostgREST with the
                      anon key).
* ``authenticated`` - SELECT/INSERT/UPDATE/DELETE, row-filtered by RLS.
* ``service_role``  - SELECT/INSERT/UPDATE/DELETE.  Supabase marks this role
                      ``BYPASSRLS`` by design; it is the trusted server-side
                      path (and what the ``supabase-py`` admin client uses).

TRUNCATE is deliberately **not** granted to ``anon``/``authenticated``:
TRUNCATE is *not* subject to RLS, so holding it would let a caller destroy
rows that RLS otherwise protects.  It is revoked from them explicitly because
Supabase's default ACL hands it out.

No ``ALTER DEFAULT PRIVILEGES`` is added on purpose: future tables must stay
deny-by-default and be granted explicitly.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7d5ff3e7ecf8'
down_revision: Union[str, None] = '79f3f70e21fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every table that participates in the RLS contract.
JARUMBA_TABLES: tuple[str, ...] = (
    "profiles",
    "favorites",
    "playlists",
    "playlist_tracks",
    "recently_played",
)

# Privileges that RLS policies can actually constrain.
DML_PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE"

# Non-DML privileges Supabase grants by default.  ``TRUNCATE`` bypasses RLS
# entirely, so the API roles must not keep it.  ``MAINTAIN`` was added in
# PostgreSQL 17; local and hosted PostgreSQL 16 must remain supported.
UNSAFE_PRIVILEGES = "TRUNCATE, REFERENCES, TRIGGER"


def _unsafe_privileges() -> str:
    """Return privileges supported by the connected PostgreSQL server."""
    bind = op.get_bind()
    version = getattr(bind.dialect, "server_version_info", ())
    if version and version[0] >= 17:
        return f"{UNSAFE_PRIVILEGES}, MAINTAIN"
    return UNSAFE_PRIVILEGES


def upgrade() -> None:
    """Give the API roles exactly the table privileges RLS can constrain."""
    tables = ", ".join(JARUMBA_TABLES)

    # 1. Deny-by-default: strip everything, including the TRUNCATE that
    #    Supabase's default ACL would otherwise leave in place.
    op.execute(sa.text(f"REVOKE ALL ON TABLE {tables} FROM anon"))
    op.execute(sa.text(f"REVOKE ALL ON TABLE {tables} FROM authenticated"))

    # 2. TRUNCATE/REFERENCES/TRIGGER/MAINTAIN are not filtered by RLS, so they
    #    are revoked from the user-facing roles without being re-granted.
    privileges = _unsafe_privileges()
    op.execute(sa.text(f"REVOKE {privileges} ON TABLE {tables} FROM anon"))
    op.execute(
        sa.text(f"REVOKE {privileges} ON TABLE {tables} FROM authenticated")
    )

    # 3. The only role that may touch user data is ``authenticated``; the RLS
    #    policies decide *which* rows.  ``anon`` receives nothing.
    op.execute(
        sa.text(f"GRANT {DML_PRIVILEGES} ON TABLE {tables} TO authenticated")
    )

    # 4. ``service_role`` is Supabase's BYPASSRLS server-side role.  It needs
    #    DML to be usable; RLS is bypassed for it by Supabase's own design.
    op.execute(
        sa.text(f"GRANT {DML_PRIVILEGES} ON TABLE {tables} TO service_role")
    )

    # 5. Sequences are not used (identifiers are UUIDs), but the FK/uniqueness
    #    machinery may consult them; keep the API roles unable to touch them.


def downgrade() -> None:
    """Restore the default privileges of the previous revision.

    Reverts to Supabase's pre-migration state: the API roles keep only the
    non-DML privileges they shipped with, and no role has DML on user tables.
    """
    tables = ", ".join(JARUMBA_TABLES)

    op.execute(sa.text(f"REVOKE ALL ON TABLE {tables} FROM anon"))
    op.execute(sa.text(f"REVOKE ALL ON TABLE {tables} FROM authenticated"))
    op.execute(sa.text(f"REVOKE ALL ON TABLE {tables} FROM service_role"))

    # Re-instate the Supabase default (``Dxtm``) for the three API roles.
    for role in ("anon", "authenticated", "service_role"):
        op.execute(
            sa.text(f"GRANT {_unsafe_privileges()} ON TABLE {tables} TO {role}")
        )
