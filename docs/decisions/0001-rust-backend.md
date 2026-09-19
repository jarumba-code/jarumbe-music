# ADR 0001: Use Rust and Axum for the Backend

## Status

Superseded.  The backend was implemented in **Python with FastAPI** (with
SQLAlchemy and Alembic) rather than Rust with Axum; [ADR 0005: Use Alembic for
Database Migrations](0005-alembic-migrations.md) records the migration-stack
decision that followed.  This ADR is retained as a record of the original
reasoning and is no longer in effect.

## Context

Jarumba Music requires a backend API for authentication verification, music
provider integration, playlists, likes, listening history, and security
controls.

The project is also intended to serve as a software engineering learning
project. The backend should provide strong type safety, predictable
performance, asynchronous request handling, and an opportunity to develop
systems programming skills.

## Options Considered

### Python with FastAPI

FastAPI would provide rapid development and is familiar for Python-based API
development. However, using it would provide less opportunity to develop the
Rust skills that are a major learning objective of this project.

### Node.js

Node.js provides a mature ecosystem and strong support for web applications.
However, it is not the preferred backend language for this project.

### Rust with Axum

Rust provides strong compile-time guarantees, memory safety, predictable
performance, and a powerful type system. Axum provides the web framework and
integrates well with Rust's asynchronous ecosystem.

## Decision

The backend will use Rust with Axum and Tokio.

The backend will initially be implemented as a modular monolith.

## Consequences

### Positive

- Strong compile-time guarantees
- Memory safety
- Good performance
- Async support
- Strong Rust engineering learning opportunity
- Clear separation between application layers

### Negative

- Higher learning curve than FastAPI
- More explicit error and type handling
- Development may initially be slower
- Smaller web ecosystem than Python or JavaScript

## Revisit Conditions

This decision may be revisited if the project's requirements change
significantly or if Rust becomes a demonstrated productivity or maintenance
problem.