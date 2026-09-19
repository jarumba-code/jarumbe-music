"""Unit tests for the harden_rls_auto_enable migration (b4e1f9a2c7d3).

These tests verify the migration file statically — the same pattern used by
``test_rls.py`` — asserting that the security fix:

* revokes EXECUTE from PUBLIC, anon and authenticated on the exact signature,
* moves the function out of the API-exposed ``public`` schema,
* does NOT weaken RLS in any way (no disabled RLS, no dropped policies),
* and is properly chained onto the existing migration history.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _migration_source() -> str:
    """Return the source of the harden_rls_auto_enable migration."""
    matches = sorted(MIGRATIONS_DIR.glob("*harden_rls_auto_enable.py"))
    assert matches, "harden_rls_auto_enable migration file is missing"
    return matches[-1].read_text(encoding="utf-8")


def _upgrade_section(source: str) -> str:
    return source.split("def downgrade()", 1)[0]


def _downgrade_section(source: str) -> str:
    return source.split("def downgrade()", 1)[1]


def test_revision_chain_is_intact():
    """The migration must extend 7d5ff3e7ecf8, not fork history."""
    source = _migration_source()
    assert re.search(r"^revision:\s*str\s*=\s*\"b4e1f9a2c7d3\"", source, re.M)
    assert re.search(r"^down_revision:[\s\S]*?=\s*\"7d5ff3e7ecf8\"", source, re.M)


def test_execute_revoked_from_public_anon_and_authenticated():
    """EXECUTE must be revoked from every API-reachable grantee."""
    upgrade = _upgrade_section(_migration_source())
    for grantee in ("PUBLIC", "anon", "authenticated"):
        assert (
            f"REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM {grantee}"
            in upgrade
        ), f"missing REVOKE for {grantee}"


def test_function_moved_out_of_public_schema():
    """The function must leave the Data API-exposed 'public' schema."""
    upgrade = _upgrade_section(_migration_source())
    assert (
        "ALTER FUNCTION public.rls_auto_enable() SET SCHEMA jarumba_admin" in upgrade
    )


def test_function_body_and_security_definer_untouched():
    """The fix must not rewrite the guard's logic."""
    source = _migration_source()
    assert "ALTER FUNCTION" in source
    assert "SECURITY INVOKER" not in source
    # No ALTER FUNCTION ... SECURITY statement may appear (that would flip
    # DEFINER/INVOKER); mentions in comments/docstrings are irrelevant.
    assert re.search(r"ALTER FUNCTION[^;]*\bSECURITY\b", source) is None
    assert "CREATE OR REPLACE FUNCTION" not in source
    assert "CREATE POLICY" not in source
    assert "DROP POLICY" not in source


def test_migration_does_not_weaken_rls():
    """No RLS may be disabled, bypassed, or removed by this migration."""
    source = _migration_source()
    assert "DISABLE ROW LEVEL SECURITY" not in source
    assert "FORCE ROW LEVEL SECURITY" not in source  # would alter policy evaluation
    assert "BYPASSRLS" not in source


def test_downgrade_restores_prior_state():
    """Downgrade must reverse both the schema move and the privilege change."""
    downgrade = _downgrade_section(_migration_source())
    assert (
        "ALTER FUNCTION jarumba_admin.rls_auto_enable() SET SCHEMA public" in downgrade
    )
    assert "GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO PUBLIC" in downgrade
