# Local development

## Managed worktrees for parallel tasks

From a **clean, retained checkout** on the desired starting commit:

```bash
make worktree-create NAME=recipe-search
```

This creates branch `codex/recipe-search` in a sibling directory of the main
checkout: `<main-checkout-name>-worktrees/recipe-search`. Use the printed path,
then run `make setup` and `make dev-start` there. Repeat with another unique name
for another task. Python 3.10+ and Git are sufficient for lifecycle commands;
the app itself uses Python 3.12. No Docker or virtualenv is needed to create an
environment. The source checkout must be clean so uncommitted work is not
silently omitted. No `.env`, production data, or existing virtualenv is copied.

Names contain up to 48 lowercase letters, digits and hyphens, starting with a
letter or digit. Each gets a named branch (not detached HEAD). Existing paths,
names and branches are never overwritten. To select a different base commit:

```bash
python3 scripts/dev_worktree.py create recipe-search --base origin/main
```

`make worktree-list` lists this repository's managed names, branches and paths.
Ownership records live under `dev-worktrees/` in the shared Git directory,
outside the disposable worktrees. Lifecycle commands are serialized with a
registry lock. The registry does not adopt existing manual or app-managed trees.

### Finishing an environment

Keep servers and worktrees until you have finished testing; ending an agent
turn is not a cleanup signal. Ask the agent to "finish environment recipe-search"
when ready. Close its named Playwright session first if one was opened. From
the retained checkout (not the worktree you are removing), run:

```bash
make worktree-check NAME=recipe-search
make worktree-finish NAME=recipe-search
```

The check does not stop the server or delete files, but fetches `origin` to
refresh publication evidence. Finish repeats the checks, stops only that server,
waits for its lock, checks again, then uses `git worktree remove` **without force**.
It retains `codex/recipe-search`, so the name cannot be reused until the retained
branch is separately dealt with. Prefer a new name for a new task.

Removal is refused for uncommitted/staged/untracked work, locked/detached/switched
worktrees, unexpected identity changes, or any HEAD not contained in a freshly
fetched `origin` branch. Fetch failure also refuses removal. Commits preserved
only in a local branch or tag do not suffice. Squash-merged branches may need
manual review because their original commits are not ancestors of the squash.
The helper never commits, pushes, deletes branches, or changes production.

**Finishing discards the environment's scratch SQLite database, logs, virtualenv
and caches.** Preserve any wanted test data first. Specifically, allowed ignored
outputs are `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, Python
`__pycache__/` directories, and the known `.dev/` database/sidecars, log, lock,
session JSON and control socket. Other ignored files—including `.env`, legacy
`data/` databases, and unknown `.dev/` files—block cleanup. Do not store valuable
files inside disposable cache/venv directories. Symlinked dev state is rejected.

If a guard fails, the worktree stays. Resolve/preserve the reported files or
publish commits with the user's authorization, then retry. A late failure after
shutdown can leave the server stopped, but the worktree retained; restart with
`make dev-start` if needed. If socket access is denied, rerun with the appropriate
command permission; do not disable sandbox protections globally. Do not edit or
restart the same environment concurrently with finish. Other environments can
continue normally. There is no age-based cleanup or background deletion service.

## Running the app

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) once on
the Mac or VPS, then run this in each worktree:

```bash
make setup
make dev-start
```

`make setup` creates a worktree-local Python 3.12 `.venv`. `make dev-start`
launches a detached Flask server and waits for its session to report ready.
It writes output to `.dev/server.log` and runs independently of the launching
shell. Use `make dev` instead when you want a foreground server in an
interactive terminal. The server reserves its own port and binds to
the host's Tailscale IPv4 address when available, otherwise to `127.0.0.1`.
It prints the URL and records it in `.dev/session.json`. `DEV_HOST=127.0.0.1
make dev-start` forces local-only access. Binding to public interfaces is refused.

Each worktree has its own `.dev/recipes.db`, process control socket, and
Playwright session name. Its SQLite database is never taken from `.env` or the
production `/srv/recipe-manager/data` path. The launcher forces development
mode. Flask's auto-reloader is disabled in this prototype; restart the server
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
- `make dev` — run the server in the foreground instead of detached
- `make dev-prune` — remove stale run metadata after a crash or reboot, keeping SQLite data
- `make dev-clean` — after stopping, remove only this worktree's development SQLite data
- `make test` — run pytest in this worktree's virtualenv
- `make typecheck` — run mypy in this worktree's virtualenv

The detached server keeps running after a phone disconnect or Codex chat ends.
Use `make dev-stop` explicitly when you no longer need the server. It waits for the
server to finish shutting down before returning, so `make dev-clean` can follow.
Check `.dev/server.log` if startup fails or the server exits unexpectedly.
`make dev-prune` handles stale metadata but does not terminate another process.
Use `make dev-clean` when the worktree's scratch database is no longer needed.
If Codex starts the server outside its command sandbox, stopping it may also
need an outside-sandbox command approval. `make dev-status` still reads the
recorded URL and checks the worktree lock when the control socket is inaccessible.
Docker is used for production images and deployment. Development and tests use
the Python environment described here.

## Running tests

```bash
make test
```

The suite runs in the worktree's `.venv`. External services are mocked, and
each test gets an isolated SQLite database under a temp directory. CI runs the
same `make setup`, `make test` and `make typecheck` commands with Python 3.12.

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
tests/                     # Pytest suite
compose.yml                # Base production Compose settings
compose.prod.yml           # Self-hosted VM overrides
railway.toml               # Railway build/deploy config
docs/                      # Additional guides
```
