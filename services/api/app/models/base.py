"""Shared base for the Jarumba ORM models.

``Base`` lives in :mod:`app.database` (alongside the engine and session
factory) so the whole project has exactly **one** declarative base.  Having
two bases would silently split the SQLAlchemy metadata registry and cause
``create_all`` to miss tables.
"""

from datetime import datetime, timezone

from app.database import Base

__all__ = ["Base", "utcnow"]


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)
