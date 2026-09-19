# ADR 0003: Monolith-First Backend

## Status

Accepted.  (Written after ADR 0001; the single-service decision carries over
unchanged to the Python/FastAPI implementation described there.)

## Context

Jarumba Music targets roughly 100 initial users.  The backend must cover
authentication verification, music-provider integration, playlists, likes,
listening history, and security controls.  The team is small and the product
is early: operational overhead must stay low while the domain boundaries are
still being learned.

## Options Considered

### Modular monolith (single deployable service)

One codebase and one deployment unit; internal modules (auth, music,
playlists, history) keep clear boundaries that can be extracted later.

### Microservices from day one

Independent scaling and deployment per domain, at the cost of distributed
transactions, service discovery, and a much heavier operations burden.

## Decision

Start with a modular monolith: a single FastAPI application
(`services/api`) with clearly separated layers (routes -> dependencies ->
services/repositories -> models/providers).  Extract a service only when a
measured, concrete need appears.

## Consequences

- One deployment unit; simple local development and CI.
- Domain boundaries are enforced by module structure, not network hops.
- Refactoring across domains is cheap while the product is young.
- A premature split is avoided; the boundaries stay ready for extraction.

## Revisit Conditions

Sustained, measured load isolated to one domain, an organisational need for
independent deployment, or a hard isolation requirement (security or
compliance) would justify extracting a service.

