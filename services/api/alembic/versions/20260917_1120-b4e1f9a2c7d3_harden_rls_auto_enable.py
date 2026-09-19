"""harden_rls_auto_enable

Revision ID: b4e1f9a2c7d3
Revises: 7d5ff3e7ecf8
Create Date: 2026-09-17 11:20:00.000000+00:00

Lock down public.rls_auto_enable() (Supabase security advisor finding).

Investigation summary
---------------------
``public.rls_auto_enable()`` is the body of the ``ensure_rls`` event trigger
(``ddl_command_end``): it auto-enables row level security on every new table
created in the ``public`` schema.  It is an intentional, beneficial
defense-in-depth guard and must be KEPT (removing it would weaken the
database's security posture, not strengthen it).

The finding exists because PostgreSQL's default function ACL grants EXECUTE
to PUBLIC, so PostgREST exposed it at ``/rest/v1/rpc/rls_auto_enable`` to
``anon`` and ``authenticated`` as a SECURITY DEFINER function owned by
``postgres``.  The function itself is only useful inside an event trigger
(``pg_event_trigger_ddl_commands()`` fails outside that context), so no
client ever has a legitimate reason to call it.

Remediation (no change to the function body or its SECURITY DEFINER):

1. ``REVOKE EXECUTE`` from ``PUBLIC``, ``anon`` and ``authenticated``.
   Event triggers are NOT affected: PostgreSQL checks EXECUTE on the trigger
   function at ``CREATE EVENT TRIGGER`` time, not again at firing time, so
   the ``ensure_rls`` guard keeps working.
2. Move the function out of ``public`` (the Data API-exposed schema) into a
   dedicated ``jarumba_admin`` schema, so it is unreachable via PostgREST
   regardless of any future privilege changes.  Event triggers bind to the
   function OID, which ``SET SCHEMA`` preserves.

This migration does NOT touch any RLS policy, table, or the RLS guard's
logic.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b4e1f9a2c7d3"
down_revision: Union[str, None] = "7d5ff3e7ecf8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make rls_auto_enable() uncallable by API roles and unexposed by PostgREST."""
    # Both steps are guarded with to_regprocedure(): on a fresh Supabase
    # project (e.g. a dedicated development database) the ensure_rls guard may
    # not exist at all, and this migration must still apply cleanly there.

    # 1. Remove every path by which a client could reach the function.
    #    Revoking from PUBLIC removes PostgreSQL's default grant; the explicit
    #    revokes from anon/authenticated also defend against a future PUBLIC
    #    re-grant.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF to_regprocedure('public.rls_auto_enable()') IS NOT NULL THEN
                    REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC;
                    REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM anon;
                    REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM authenticated;
                END IF;
            END
            $$;
            """
        )
    )

    # 2. Move the guard out of the API-exposed 'public' schema entirely.
    #    PostgREST only exposes configured schemas, so a non-exposed admin
    #    schema makes the function unreachable via /rest/v1/rpc by design.
    #    'ensure_rls' keeps working: event triggers reference the function
    #    OID, which SET SCHEMA does not change.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF to_regprocedure('public.rls_auto_enable()') IS NOT NULL THEN
                    CREATE SCHEMA IF NOT EXISTS jarumba_admin AUTHORIZATION postgres;
                    ALTER FUNCTION public.rls_auto_enable() SET SCHEMA jarumba_admin;
                    COMMENT ON FUNCTION jarumba_admin.rls_auto_enable() IS
                        'Body of the ensure_rls event trigger; enables RLS on new tables in the public schema. Admin-only; intentionally NOT executable by anon/authenticated and NOT exposed via the Data API.';
                END IF;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    """Restore the pre-hardening state (default ACL behaviour and location)."""
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF to_regprocedure('jarumba_admin.rls_auto_enable()') IS NOT NULL THEN
                    ALTER FUNCTION jarumba_admin.rls_auto_enable() SET SCHEMA public;
                    DROP SCHEMA IF EXISTS jarumba_admin RESTRICT;
                    -- Restore PostgreSQL's default (PUBLIC may EXECUTE functions).
                    GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO PUBLIC;
                END IF;
            END
            $$;
            """
        )
    )

