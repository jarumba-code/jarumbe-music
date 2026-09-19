"""Stub for tables owned by Supabase Auth.

``profiles.id`` references ``auth.users.id``.  Supabase owns the ``auth``
schema, so Jarumba must **not** create or migrate it.  Registering this
lightweight :class:`~sqlalchemy.Table` stub in our metadata lets SQLAlchemy
resolve the foreign key (and emit correct DDL) without taking ownership of
the table.
"""

from __future__ import annotations

from sqlalchemy import Column, Table
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.models.base import Base

AUTH_SCHEMA = "auth"

#: Read-only reflection stub for ``auth.users``.
#:
#: ``info={"external": True}`` marks the table so tooling (and the test
#: helpers) can exclude it from ``CREATE TABLE`` operations.  It carries only
#: the primary key column, which is all our foreign keys need to resolve.
auth_users = Table(
    "users",
    Base.metadata,
    Column("id", PG_UUID(as_uuid=False), primary_key=True),
    schema=AUTH_SCHEMA,
    info={"external": True, "owner": "supabase-auth"},
)

__all__ = ["AUTH_SCHEMA", "auth_users"]