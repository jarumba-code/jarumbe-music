"""Listening-history endpoints — identity and scoping come from the JWT only.

Rate limiting is attached at the route level (``dependencies=[...]``) so it is
resolved before JWT verification; an invalid token is charged to the anonymous
(IP) bucket rather than bypassing the limiter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import PaginationParams, rate_limiter
from app.api.routes.auth import get_current_user_id
from app.database import get_db
from app.models.recently_played import RecentlyPlayed
from app.schemas.recently_played import RecentlyPlayedCreate, RecentlyPlayedRead
from app.services.auth import ensure_profile_exists

router = APIRouter()


@router.get(
    "/recently-played",
    response_model=list[RecentlyPlayedRead],
    dependencies=[Depends(rate_limiter("recently_played"))],
)
def list_my_history(
    pagination: PaginationParams = Depends(),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[RecentlyPlayed]:
    """The authenticated user's play history, most recent first.

    Paginated (``limit`` 1-100, ``offset`` >= 0) and scoped to the verified JWT
    identity, so one user can never read another user's history.  There is no
    retention policy in the current documented requirements, so the full history
    is retained and only windowed per request.
    """
    return list(
        db.execute(
            select(RecentlyPlayed)
            .where(RecentlyPlayed.user_id == user_id)
            .order_by(RecentlyPlayed.played_at.desc())
            .offset(pagination.offset)
            .limit(pagination.limit)
        ).scalars()
    )


@router.post(
    "/recently-played",
    response_model=RecentlyPlayedRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limiter("recently_played"))],
)
def record_play(
    payload: RecentlyPlayedCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecentlyPlayed:
    """Record one play event for the authenticated user.

    History is append-only and intentionally permits repeated plays of the same
    track (there is no uniqueness constraint on the track reference).
    ``user_id`` comes from the verified JWT — a user_id in the request body is
    neither accepted nor stored.  The profile row is ensured first so the
    ``recently_played.user_id -> profiles.id`` foreign key cannot fail for a
    brand-new verified user.
    """
    ensure_profile_exists(db, user_id)

    entry = RecentlyPlayed(
        user_id=user_id,
        provider=payload.provider,
        provider_track_id=payload.provider_track_id,
        title=payload.title,
        artist=payload.artist,
        album=payload.album,
        duration=payload.duration,
        artwork_url=payload.artwork_url,
        license_url=payload.license_url,
        license_name=payload.license_name,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry