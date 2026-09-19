"""Music providers package.

This package contains the provider abstraction layer that isolates Jarumba
from third-party music provider response formats.  Each provider normalizes
its raw API responses into the shared :class:`~app.providers.base.Track`
dataclass so the rest of the application never depends on Jamendo-specific
fields.
"""

from app.providers.base import (
    BaseProvider,
    ProviderError,
    ProviderResponseError,
    ProviderUnavailableError,
    Track,
)
from app.providers.jamendo import JamendoProvider

__all__ = [
    "BaseProvider",
    "Track",
    "ProviderError",
    "ProviderUnavailableError",
    "ProviderResponseError",
    "JamendoProvider",
]
