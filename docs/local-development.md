# Local development

## Running the app

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) once on
the Mac or VPS, then run this in each worktree:

```bash
make setup
make dev
```

`make setup` creates a worktree-local Python 3.12 `.venv`. `make dev` starts a
foreground Flask server on a port reserved by the server itself. It binds to
the host's Tailscale IPv4 address when available, otherwise to `127.0.0.1`.
It prints the URL and records it in `.dev/session.json`. `DEV_HOST=127.0.0.1
make dev` forces local-only access. Binding to public interfaces is refused.

Each worktree has its own `.dev/recipes.db`, process control socket, and
Playwright session name. Its SQLite database is never taken from `.env` or the
production `/srv/recipe-manager/data` path. The launcher forces development
mode. Flask's auto-reloader is disabled in this prototype; restart `make dev`
after Python code changes. Template and static changes appear on page refresh.

On the VPS, use the `url` and `playwright_session` from `.dev/session.json`:

```bash
playwright-cli -s=<playwright_session> open <url>
playwright-cli -s=<playwright_session> snapshot
playwright-cli -s=<playwright_session> console
playwright-cli -s=<playwright_session> close
```

Always close that named browser session when finished. Do not use
`playwright-cli close-all`, which would affect other worktrees.

Without `.env`, authentication is disabled for development and extraction
features requiring Anthropic credentials will not work. To test those features,
create a worktree-local `.env` with development credentials. Never copy the
production environment file into a worktree.

Useful commands:

- `make dev-status` — show the exact URL, database and Playwright session
- `make dev-stop` — stop only this worktree's development server
- `make dev-prune` — remove stale run metadata after a crash or reboot, keeping SQLite data
- `make dev-clean` — after stopping, remove only this worktree's development SQLite data
- `make test` — run pytest in this worktree's virtualenv
- `make typecheck` — run mypy in this worktree's virtualenv
- `make docker-test` — run the existing container test suite used by CI
- `make docker-dev` — run the legacy Compose development stack when specifically needed

The foreground command may continue running after a phone disconnect or a
Codex chat ends. Use `make dev-stop` explicitly at the end of a work session.
`make dev-prune` handles stale metadata but does not terminate another process.
Use `make dev-clean` when the worktree's scratch database is no longer needed.
If Codex starts the server outside its command sandbox, stopping it may also
need an outside-sandbox command approval. `make dev-status` still reads the
recorded URL and checks the worktree lock when the control socket is inaccessible.
The older Compose targets remain available for container parity checks; their
fixed `DEV_PORT` is not suitable for simultaneous worktrees.

## Running tests

```bash
make test
```

The suite runs in the worktree's `.venv`. External services are mocked, and
each test gets an isolated SQLite database under a temp directory. CI still
runs `make docker-test` while this native workflow is being validated.

## Project structure

```
app/
  __init__.py              # Flask app factory
  config.py                # Dev/prod configuration
  extraction/
    schema.py              # Recipe tool schema (single source of truth)
    jina.py                # URL content fetching via Jina Reader
    image.py               # Image preparation (resize/compress for Claude)
    claude.py              # Claude extraction orchestration
  calories/                # Per-serving calorie calculation + breakdowns
  schemas/                 # Pydantic models (recipes, calories, forms)
  storage/
    db.py                  # SQLite connection + schema init
    recipes.py             # Recipe CRUD operations
    calories.py            # Calorie lookup CRUD
  routes/
    auth.py                # Username/password auth gate
    recipes.py             # Flask blueprint with all routes (+ /health)
  templates/               # Jinja2 templates (Pico CSS + HTMX)
  static/css/app.css       # Minimal custom styles
.dev/                      # ignored native dev database and run metadata
data/                      # legacy Docker dev database
tests/                     # Pytest suite
compose.yml                # Shared Compose settings
compose.dev.yml            # Local development + test overrides
compose.prod.yml           # Self-hosted VM overrides
railway.toml               # Railway build/deploy config
docs/                      # Additional guides
```
