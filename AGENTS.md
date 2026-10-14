# AGENTS.md

## Project Overview

Recipe Manager is a small Flask web app for extracting recipes from URLs and images, then storing them in a local SQLite database.

Main stack:

- Flask app factory in `app/__init__.py`
- Server-rendered Jinja templates in `app/templates/`
- SQLite access in `app/storage/`
- Extraction logic in `app/extraction/`
- Username/password authentication gate in `app/routes/auth.py`
- Main product routes in `app/routes/recipes.py`

## Local Development

Use a worktree-local Python environment for development. Docker remains for
production images and optional container checks.

Primary commands:

- `make setup` to create a Python 3.12 `.venv` with uv
- `make dev-start` to start the app persistently for Codex or remote sessions
- `make dev` to run it in the foreground from an interactive terminal
- `make dev-status` to find its allocated URL and Playwright session name
- `make dev-stop` to stop only this worktree's app
- `make dev-clean` when its scratch SQLite data is no longer needed
- `make test` to run pytest in the virtualenv
- `make docker-test` for the CI container check

**For LLM agents (Claude, Codex, etc.):** work in a separate Git worktree.
Run `make setup` there once, then `make dev-start` and `make test`. Use the URL and
Playwright session reported by `.dev/session.json`. Stop the server with
`make dev-stop` when the work is complete. Do not run ordinary development
commands against production Compose files, containers, or `/srv` data.

Underlying Compose usage:

- optional container development uses `docker compose -f compose.yml -f compose.dev.yml up`
- production uses `docker compose -f compose.yml -f compose.prod.yml up -d`

Notes:

- Native dev binds to a dynamically allocated loopback or Tailscale port
- Its SQLite database lives at `.dev/recipes.db` in this worktree
- The legacy Docker dev database lives at `data/recipes.db`

## Environment And Auth

Required environment variables in `.env`:

- `ANTHROPIC_API_KEY`
- `SECRET_KEY`
- `AUTH_USERNAME` and `AUTH_PASSWORD` when `AUTH_ENABLED=true`

Optional:

- `DATABASE_PATH` (native dev always overrides this to `.dev/recipes.db`)

Auth behavior:

- Native dev disables auth by default when no `.env` sets `AUTH_ENABLED`
- If auth is enabled, set `AUTH_USERNAME` and `AUTH_PASSWORD`

Important:

- `app/__init__.py` validates username/password auth config at startup
- `app/__init__.py` rejects the default `SECRET_KEY` in production

## Testing

Run:

- `make test`

Each test gets an isolated SQLite DB under a pytest `tmp_path`.

When changing auth, routing, storage, or config:

- Add or update tests in `tests/test_auth.py`, `tests/test_routes.py`, or `tests/test_recipes_storage.py`

## Key Files

- `compose.yml`: shared Compose settings
- `compose.dev.yml`: optional container development and CI test overrides
- `compose.prod.yml`: production VM overrides
- `Dockerfile`: shared image for app and tests
- `Makefile`: standard developer entrypoints
- `app/config.py`: app configuration and credentials
- `app/__init__.py`: app factory and startup validation (calls `init_db`)
- `app/storage/db.py`: SQLite connection management and schema init
- `app/storage/recipes.py`: Recipe CRUD
- `app/routes/auth.py`: login, callback, logout, and auth guard
- `README.md`: user-facing setup notes

## Implementation Notes

- The app uses session-based auth after username/password login
- HTMX requests are handled specially in the auth guard via `HX-Redirect`
- `ProxyFix` is enabled so callback URLs and scheme handling work correctly behind proxies
- The SQLite schema is created on startup via `CREATE TABLE IF NOT EXISTS`; `ingredients`, `steps`, and `tags` are stored as JSON TEXT columns

## Working Style For Future Sessions

- Prefer small, surgical changes
- Preserve the worktree-local native workflow
- Update `README.md` when changing setup, commands, or auth requirements
- Verify meaningful changes with `make test`
- If changing auth or startup validation, make sure the app still boots in Docker
