"""Server-side music-provider registry.

Jarumba stores tracks as *provider references*, so every client payload that
carries a ``provider`` value must be validated against the providers this
backend actually implements — never against a value the client chooses.

Adding a provider later (for example Audiomack) means:

1. implement :class:`~app.providers.base.BaseProvider`,
2. add **one** :class:`ProviderSpec` entry to :data:`PROVIDER_REGISTRY`,
3. add a factory branch in :func:`build_provider`.

No route, schema, request model or database column needs to change: the
allow-list, the OpenAPI enum and the validation error for an unknown provider
all derive from this registry.

Only ``jamendo`` is registered today; no other provider is implemented and no
other provider is accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.providers.base import BaseProvider


class MusicProvider(str, Enum):
    """Providers the API accepts in request payloads.

    Used directly as a Pydantic field type, which makes the allow-list part of
    the generated OpenAPI schema (an unknown value is a 422 validation error).
    """

    JAMENDO = "jamendo"


@dataclass(frozen=True)
class ProviderSpec:
    """Static description of one supported provider."""

    name: str
    #: True only for providers whose stream/download URLs remain valid for at
    #: least the search-cache TTL.  Providers that hand out short-lived signed
    #: URLs must set this to False so the cache layer never stores them.
    cacheable_stream_urls: bool = True


#: The authoritative provider allow-list, keyed by provider name.
PROVIDER_REGISTRY: dict[str, ProviderSpec] = {
    MusicProvider.JAMENDO.value: ProviderSpec(
        name=MusicProvider.JAMENDO.value,
        cacheable_stream_urls=True,
    ),
}


class UnsupportedProviderError(ValueError):
    """Raised when a client supplies a provider the backend does not support."""


def supported_provider_names() -> tuple[str, ...]:
    """All provider names accepted in request payloads."""
    return tuple(sorted(PROVIDER_REGISTRY))


def is_supported_provider(value: object) -> bool:
    """True when *value* names a provider this backend implements."""
    return isinstance(value, str) and value in PROVIDER_REGISTRY


def validate_provider(value: object) -> str:
    """Return the canonical provider name or raise :class:`UnsupportedProviderError`."""
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in PROVIDER_REGISTRY:
            return candidate
    supported = ", ".join(supported_provider_names())
    raise UnsupportedProviderError(
        f"Unsupported music provider {value!r}. Supported providers: {supported}"
    )


def provider_spec(name: str) -> ProviderSpec:
    """Return the :class:`ProviderSpec` for an already-validated *name*."""
    return PROVIDER_REGISTRY[validate_provider(name)]


def build_provider(name: str, settings) -> BaseProvider:  # noqa: ANN001
    """Construct the provider implementation for *name*.

    Only Jamendo is implemented today.  The branch structure exists so a future
    provider can be added here without touching routes or schemas.
    """
    canonical = validate_provider(name)

    if canonical == MusicProvider.JAMENDO.value:
        from app.providers.jamendo import JamendoProvider

        return JamendoProvider(client_id=settings.jamendo_client_id)

    # Unreachable while the registry and the factory stay in sync; kept as a
    # hard failure so a half-registered provider can never silently pass.
    raise UnsupportedProviderError(f"Provider {canonical!r} has no factory")


__all__ = [
    "MusicProvider",
    "ProviderSpec",
    "PROVIDER_REGISTRY",
    "UnsupportedProviderError",
    "build_provider",
    "is_supported_provider",
    "provider_spec",
    "supported_provider_names",
    "validate_provider",
]