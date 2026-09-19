"""Jarumba Music SQLAlchemy ORM models.

Importing this package registers every model on the shared
:class:`app.database.Base` metadata, which is what migration tooling and
``Base.metadata.create_all`` rely on.
"""

from app.models.base import Base, utcnow
from app.models.external import AUTH_SCHEMA, auth_users
from app.models.favorite import Favorite
from app.models.playlist import Playlist
from app.models.playlist_track import PlaylistTrack
from app.models.profile import Profile
from app.models.recently_played import RecentlyPlayed

__all__ = [
    "Base",
    "utcnow",
    "AUTH_SCHEMA",
    "auth_users",
    "Profile",
    "Favorite",
    "Playlist",
    "PlaylistTrack",
    "RecentlyPlayed",
]

#: Domain tables owned and migrated by Jarumba (excludes the Supabase
#: ``auth.users`` stub, which Supabase owns).
DOMAIN_TABLES = (
    Profile.__table__,
    Favorite.__table__,
    Playlist.__table__,
    PlaylistTrack.__table__,
    RecentlyPlayed.__table__,
)
