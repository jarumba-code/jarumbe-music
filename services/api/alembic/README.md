# Alembic migration environment

Versioned schema migrations for the Jarumba Music PostgreSQL database.

## Why the database URL is not in `alembic.ini`

`alembic/env.py` resolves the connection string from
`app.config.get_settings()`, i.e. the same `DATABASE_URL` the FastAPI
application already uses (loaded from the environment or `services/api/.env`).
This guarantees:

* migrations always target the same database the API talks to;
* the Supabase connection string is never committed to the repository.

## Common commands

Run all commands from `services/api`.

```bash
# create a migration from model changes
alembic revision --autogenerate -m "describe the change"

# apply all pending migrations
alembic upgrade head

# roll back one migration
alembic downgrade -1

# show the currently applied revision
alembic current

# print the SQL a migration would run, without connecting
alembic upgrade head --sql
```

## What Alembic manages

Only the tables Jarumba owns:

* `profiles`
* `favorites`
* `playlists`
* `playlist_tracks`
* `recently_played`

`auth.users` is owned by Supabase Auth. It is registered in the SQLAlchemy
metadata as a read-only stub (so `profiles.id -> auth.users.id` resolves) and
is explicitly excluded from autogeneration in `env.py` via `include_object`.
