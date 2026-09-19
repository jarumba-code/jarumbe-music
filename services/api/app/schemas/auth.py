"""Auth-related Pydantic schemas for the public API contract."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class AuthMeResponse(BaseModel):
    """Minimal response for ``GET /api/v1/auth/me``.

    Returns only the authenticated Supabase user UUID.  No other profile
    fields, email, or OAuth information is exposed through this foundation
    endpoint.
    """

    id: UUID = Field(..., description="Authenticated Supabase user UUID (auth.users.id)")


__all__ = ["AuthMeResponse"]
