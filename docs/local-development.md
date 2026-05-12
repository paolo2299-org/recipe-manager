# Local development

## Running the app

```bash
cp .env.example .env       # then set ANTHROPIC_API_KEY and SECRET_KEY
make dev
```

The app is available at `http://localhost:8080` with Flask hot reload enabled.

Useful commands:

- `make dev` — start the app
- `make test` — run the pytest suite inside Docker
- `make typecheck` — run mypy
- `make shell` — open a shell inside the running app container
- `make down` — stop and remove the local containers

If `.env` is missing, the `make` targets fall back to `.env.example` so config validation
and teardown still work in a fresh checkout. To run against real credentials, copy
`.env.example` to `.env` and fill in the secrets.

## Running tests

```bash
make test
```

The suite runs inside Docker. External services are mocked, and each test gets an isolated
SQLite database under a temp directory.

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
data/                      # SQLite database lives here (bind-mounted / volume)
tests/                     # Pytest suite
compose.yml                # Shared Compose settings
compose.dev.yml            # Local development + test overrides
compose.prod.yml           # Self-hosted VM overrides
railway.toml               # Railway build/deploy config
docs/                      # Additional guides
```
