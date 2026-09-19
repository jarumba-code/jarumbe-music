# ADR 0004: Music Provider Architecture

## Status

Accepted for the current milestone.  **Jamendo is the only ACTIVE provider.**
Audiomack is PLANNED and explicitly DEFERRED — it is NOT implemented.

## Context

Jarumba stores tracks as *provider references* (`provider` +
`provider_track_id`) plus a metadata snapshot; it never stores audio.  Client
input names a provider, so the backend needs a single server-side
allow-list that every consumer (favorites, playlist tracks, recently played,
search) validates against — never a client-chosen value.

## Decision

* `app.providers.registry` is the single source of truth:
  `MusicProvider` (the Pydantic/OpenAPI enum), `PROVIDER_REGISTRY`
  (name → `ProviderSpec`), and `build_provider` (name → implementation).
* Only `jamendo` is registered today.  Unknown provider values are a 422
  validation error.
* Adding a provider (e.g. Audiomack) requires implementing
  `BaseProvider`, one registry entry, and one factory branch — no route,
  schema, or database change.
* `ProviderSpec.cacheable_stream_urls` marks whether stream/download URLs may
  be cached.  Jamendo URLs are stable enough for the short search-cache TTL;
  a provider that issues short-lived signed URLs must set this to `False`,
  and its URLs must never be long-lived cache values.
* Client-supplied license metadata is display-only; it is never treated as
  authoritative licensing evidence.

## Consequences

- Consistent provider validation across all endpoints (one contract).
- The OpenAPI schema documents the allow-list automatically.
- No provider-specific logic leaks into routes or schemas.

## Revisit Conditions

Audiomack support is revisited when its API/licensing terms are verified;
until then it remains unimplemented and unaccepted.

