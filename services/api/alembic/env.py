"""Alembic runtime environment for Jarumba Music.

Design notes
------------
* The database URL is **never** stored in ``alembic.ini``.  It is read from
  the application's existing settings (:func:`app.config.get_settings`), so
  migrations always run against exactly the database the API uses.
* ``app.models`` is imported for its side effect: importing the package
  registers every ORM model on ``Base.metadata``.  ``target_metadata`` below
  is that same metadata object.
* The Supabase-owned ``auth.users`` table is registered in our metadata as a
  read-only stub so the ``profiles.id`` foreign key can resolve.  It is
  filtered out of autogeneration/``create_all`` via ``include_object`` —
  Alembic must never create, alter, or drop a table Supabase owns.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the ``app`` package importable when Alembic is invoked from anywhere.
SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.config import get_settings  # noqa: E402
from app.models import Base, auth_users  # noqa: E402

# Alembic Config object; provides access to values in alembic.ini.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

#: Metadata describing the schema Jarumba owns.
target_metadata = Base.metadata


def _database_url() -> str:
    """Return the configured database URL, or fail loudly and safely.

    The URL is never logged — only the fact that it is missing.
    """
    url = (get_settings().database_url or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it in the environment or in "
            "services/api/.env before running Alembic."
        )
    return url


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Exclude tables that Jarumba does not own.

    ``auth.users`` belongs to Supabase Auth.  Excluding it here means
    autogenerate will not emit ``CREATE``/``DROP``/``ALTER`` for it, while
    foreign keys *pointing at* it are still emitted normally.
    """
    if type_ == "table":
        if obj is auth_users:
            return False
        if (obj.schema or None) == "auth":
            return False
        if obj.info.get("external"):
            return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (``alembic upgrade --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
        include_schemas=False,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
            # MUST stay False.  The Supabase database contains many schemas
            # that Jarumba does not own (auth, storage, realtime, vault,
            # graphql).  With include_schemas=True, autogenerate reflects all
            # of them and emits DROP TABLE for each one missing from
            # target_metadata -- which would be catastrophic.
            include_schemas=False,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
