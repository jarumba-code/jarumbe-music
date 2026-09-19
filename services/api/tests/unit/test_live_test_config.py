"""Regression tests pinning the live-RLS test-target safety rule.

The live RLS suite must be reachable ONLY through an explicit
``JARUMBA_LIVE_DATABASE_URL``. It must never fall back to ``DATABASE_URL``,
which is the normal application database configuration.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_LIVE_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "integration" / "test_rls_live.py"
)

_DUMMY_APP_URL = "postgresql+psycopg://dummy-must-never-be-used-for-live-tests"


def _load_live_module():
    """Import the live module (module-level code touches no database)."""
    spec = importlib.util.spec_from_file_location(
        "test_rls_live_config_probe", _LIVE_MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_url_is_none_without_explicit_variable(monkeypatch) -> None:
    """DATABASE_URL alone must never become the live-test target."""
    module = _load_live_module()
    monkeypatch.setenv("DATABASE_URL", _DUMMY_APP_URL)
    monkeypatch.delenv("JARUMBA_LIVE_DATABASE_URL", raising=False)
    assert module._live_database_url() is None


def test_live_url_uses_only_the_explicit_variable(monkeypatch) -> None:
    module = _load_live_module()
    monkeypatch.setenv("DATABASE_URL", _DUMMY_APP_URL)
    monkeypatch.setenv(
        "JARUMBA_LIVE_DATABASE_URL", "postgresql+psycopg://explicit-live-target"
    )
    assert module._live_database_url() == "postgresql+psycopg://explicit-live-target"


def test_live_url_empty_string_is_not_a_target(monkeypatch) -> None:
    module = _load_live_module()
    monkeypatch.setenv("DATABASE_URL", _DUMMY_APP_URL)
    monkeypatch.setenv("JARUMBA_LIVE_DATABASE_URL", "")
    assert module._live_database_url() is None


def test_flag_with_database_url_alone_cannot_enable_live(monkeypatch) -> None:
    """Even with the opt-in flag set, the suite skips without an explicit URL."""
    module = _load_live_module()
    monkeypatch.setenv("JARUMBA_RUN_LIVE_RLS", "1")
    monkeypatch.setenv("DATABASE_URL", _DUMMY_APP_URL)
    monkeypatch.delenv("JARUMBA_LIVE_DATABASE_URL", raising=False)
    # Exactly the pytestmark skipif condition evaluated in the live module:
    # skip when the flag is NOT "1" OR no explicit live URL is set.  (The
    # previous mirror of this expression was inverted: `flag_ok or not url`
    # would also assert a skip in the flag-set + URL-set scenario where the
    # live suite would actually run.)
    flag_ok = os.environ.get("JARUMBA_RUN_LIVE_RLS") == "1"
    would_skip = (not flag_ok) or (not module._live_database_url())
    assert would_skip, "live suite must skip when no explicit live URL is set"
