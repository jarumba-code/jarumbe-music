"""Favorites endpoints — every operation scoped to the verified JWT identity.

Rate limiting is attached at the route level (``dependencies=[...]``), which
FastAPI resolves before the endpoint's own parameters — so the limiter runs
before JWT verification and an invalid token cannot bypass it.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import PaginationParams, rate_limiter
from app.api.routes.auth import get_current_user_id
from app.database import get_db
from app.models.favorite import Favorite
from app.providers.registry import MusicProvider
from app.schemas.favorite import FavoriteCreate, FavoriteRead
from app.services.auth import ensure_profile_exists

router = APIRouter()

#: ``provider_track_id`` is bounded to the width of the database column.
_TRACK_ID_PATH = Path(..., min_length=1, max_length=255)


@router.get(
    "/favorites",
    response_model=list[FavoriteRead],
    dependencies=[Depends(rate_limiter("favorites"))],
)
def list_my_favorites(
    pagination: PaginationParams = Depends(),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[Favorite]:
    """The authenticated user's favorites, newest first.

    Paginated: ``limit`` (1-100) and ``offset`` (>= 0).  Scoped to the verified
    JWT identity, so another user's favorites can never be listed.
    """
    return list(
        db.execute(
            select(Favorite)
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.limit)
        ).scalars()
    )


@router.post(
    "/favorites",
    response_model=FavoriteRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limiter("favorites"))],
)
def create_favorite(
    payload: FavoriteCreate,
    response: Response,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Favorite:
    """Favourite a track for the authenticated user.

    Idempotent: a duplicate ``(user_id, provider, provider_track_id)`` returns
    the existing favorite with HTTP 200 instead of an uncontrolled database
    error.  The profile row is ensured first (a brand-new verified user may not
    have one yet), so the ``favorites.user_id -> profiles.id`` foreign key can
    never turn a valid request into a 500.
    """
    ensure_profile_exists(db, user_id)

    existing = db.execute(
        select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.provider == payload.provider,
            Favorite.provider_track_id == payload.provider_track_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing

    favorite = Favorite(
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
    db.add(favorite)
    try:
        db.commit()
    except IntegrityError as exc:
        # Raced with a concurrent duplicate insert by the same user: return the
        # row the other request committed.  Any other integrity failure is
        # reported as a controlled conflict instead of a 500.
        db.rollback()
        existing = db.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.provider == payload.provider,
                Favorite.provider_track_id == payload.provider_track_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Favorite could not be created",
            ) from exc
        response.status_code = status.HTTP_200_OK
        return existing
    db.refresh(favorite)
    return favorite


@router.delete(
    "/favorites/{provider}/{provider_track_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limiter("favorites"))],
)
def delete_favorite(
    provider: MusicProvider,
    provider_track_id: str = _TRACK_ID_PATH,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Remove one of *the authenticated user's* favorites.

    The delete is filtered by the verified ``user_id`` — a user can never
    remove another user's favorite even by guessing its track reference.  A
    missing row is a plain 404 (no existence leak for other users' data), and
    ``provider`` is validated against the server-side provider allow-list
    before any query runs.
    """
    result = db.execute(
        select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.provider == provider.value,
            Favorite.provider_track_id == provider_track_id,
        )
    ).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Favorite not found")
    db.delete(result)
    db.commit()
