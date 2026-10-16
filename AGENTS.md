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

For plain-language preview/start/stop/cleanup requests, use this repository's
`.agents/skills/dev-app/SKILL.md`. It is project-scoped on both the Mac and VPS.

Use a worktree-local Python environment for development and tests. CI uses the
same setup and commands. Docker is used for production images and deployment.

Primary commands:

- `make setup` to create a Python 3.12 `.venv` with uv
- `make dev-start` to start the app persistently for Codex or remote sessions
- `make dev` to run it in the foreground from an interactive terminal
- `make dev-status` to find its allocated URL and Playwright session name
- `make dev-stop` to stop only this worktree's app
- `make dev-clean` when its scratch SQLite data is no longer needed
- `make test` to run pytest in the virtualenv

**For LLM agents (Claude, Codex, etc.):** use a separate Git worktree. Reuse the
current task's suitable worktree rather than creating one each turn. For a new
environment, run `make worktree-create NAME=<unique-task-name>` from a clean,
retained checkout. It creates `codex/<unique-task-name>` and prints the path.
Run `make setup` there once, then `make dev-start` and `make test`. Report the
environment name, branch, path, URL and Playwright session from `.dev/session.json`.

Leave the environment and server available while the user tests or intends to
resume. A turn ending or phone disconnecting is NOT authorization to clean up.
When the user says they are finished with this environment:

1. Close only its named Playwright session if you opened one (never `close-all`).
2. From a retained checkout, run `make worktree-check NAME=<name>`.
3. If it passes, run `make worktree-finish NAME=<name>`. This stops only that
   server, removes its scratch data/logs/venv and worktree, and retains the branch.
4. Report removal and the retained branch. If a guard fails, explain what needs
   preserving and leave it in place. Do not force removal, discard changes,
   delete branches, or commit/push merely to bypass a guard without authorization.

Cleanup requires access to `origin` to verify published commits. Unexpected
ignored files (including `.env`) block removal; preserve or explicitly resolve
them with the user. Do not run competing lifecycle commands in the same
environment. Only environments created by this helper are eligible: do not
adopt or remove app-managed, manually created, or another task's worktrees.
See `docs/local-development.md` for recovery and disposable-file details.

Do not run ordinary development commands against production Compose files,
containers, or `/srv` data.

Production Compose usage: `docker compose -f compose.yml -f compose.prod.yml up -d`.

Notes:

- Native dev binds to a dynamically allocated loopback or Tailscale port
- Its SQLite database lives at `.dev/recipes.db` in this worktree

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

- `compose.yml`: base production Compose settings
- `compose.prod.yml`: production VM overrides
- `Dockerfile`: production app image
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

## Private native-development configuration

Use the project-specific host config in `docs/local-development.md` for reusable
credentials/settings. `make dev-config` reports names only. Never print secrets,
copy an entire production env, or delete host config when finishing a worktree.
Production-key provisioning requires the user's specific authorisation.
