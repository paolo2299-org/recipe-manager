# AGENTS.md

## Project Overview

Recipe Manager is a small Flask web app for extracting recipes from URLs and images, then storing them in a local SQLite database.

Main stack:

- Flask app factory in `app/__init__.py`
- Server-rendered Jinja templates in `app/templates/`
- SQLite access in `app/storage/`
- Extraction logic in `app/extraction/`
- Google OAuth gate in `app/routes/auth.py`
- Main product routes in `app/routes/recipes.py`

## Local Development

This project is set up to use Docker for local development.

Primary commands:

- `cp .env.example .env`
- `make dev` to start the app
- `make test` to run the pytest suite in Docker
- `make shell` to open a shell in the app container
- `make down` to stop local containers

**For LLM agents (Claude, Codex, etc.):** default to running tests and any
other repo code through Docker (`make test`, `make shell`, or the underlying
`docker compose` commands). Do not fall back to `python`, `pytest`, `pip`, or
`uv` on the host — the host Python environment is not guaranteed to exist or
to match the Docker image's dependencies. If a Docker command fails, debug
the container setup; do not work around it by running on the host.

Underlying Compose usage:

- local development uses `docker compose -f compose.yml -f compose.dev.yml up`
- production uses `docker compose -f compose.yml -f compose.prod.yml up -d`

Notes:

- The app runs on `http://localhost:8080`
- The SQLite database lives at `data/recipes.db` (bind-mounted into the container)
- Do not assume a host Python environment is available or correct

## Environment And Auth

Required environment variables in `.env`:

- `ANTHROPIC_API_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `SECRET_KEY`
- `GOOGLE_ALLOWED_EMAILS` when `GOOGLE_AUTH_ENABLED=true`

Optional:

- `DATABASE_PATH` (defaults to `data/recipes.db`)

Google auth behavior:

- Auth is enabled by default with `GOOGLE_AUTH_ENABLED=true`
- Allowed Google accounts come from `GOOGLE_ALLOWED_EMAILS`
- Local OAuth redirect URI must include `http://localhost:8080/auth/google/callback`

Important:

- `app/__init__.py` validates Google auth config at startup
- `app/__init__.py` rejects the default `SECRET_KEY` in production
- Keep `GOOGLE_ALLOWED_EMAILS` non-empty when auth is enabled

## Testing

Run:

- `make test`

Each test gets an isolated SQLite DB under a pytest `tmp_path`.

When changing auth, routing, storage, or config:

- Add or update tests in `tests/test_auth.py`, `tests/test_routes.py`, or `tests/test_recipes_storage.py`

## Key Files

- `compose.yml`: shared Compose settings
- `compose.dev.yml`: local app and test runner overrides
- `compose.prod.yml`: production VM overrides
- `Dockerfile`: shared image for app and tests
- `Makefile`: standard developer entrypoints
- `app/config.py`: app config and allowed Google accounts
- `app/__init__.py`: app factory and startup validation (calls `init_db`)
- `app/storage/db.py`: SQLite connection management and schema init
- `app/storage/recipes.py`: Recipe CRUD
- `app/routes/auth.py`: login, callback, logout, and auth guard
- `README.md`: user-facing setup notes

## Implementation Notes

- The app uses session-based auth after Google sign-in
- HTMX requests are handled specially in the auth guard via `HX-Redirect`
- `ProxyFix` is enabled so callback URLs and scheme handling work correctly behind proxies
- The SQLite schema is created on startup via `CREATE TABLE IF NOT EXISTS`; `ingredients`, `steps`, and `tags` are stored as JSON TEXT columns

## Working Style For Future Sessions

- Prefer small, surgical changes
- Preserve the Docker-only local workflow
- Update `README.md` when changing setup, commands, or auth requirements
- Verify meaningful changes with `make test`
- If changing Google auth or startup validation, make sure the app still boots in Docker
