# Recipe Manager

A web application for extracting and saving structured recipe data from photos, URLs,
and pasted text using the Claude API.

Upload a photo of a recipe or paste a URL, and the app uses Claude to extract structured
information — title, ingredients, steps, timings, and tags — plus optional per-serving
calorie estimates. You can also save lightweight recipe ideas with just a name, notes, and
tags. Everything is stored in a SQLite database and can be browsed, viewed, and deleted.

## Deploy it (easiest) — Railway

<!-- Replace XXXXXX with the published template ID — see docs/railway-template.md -->
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/XXXXXX)

1. Get an [Anthropic API key](https://console.anthropic.com/) (you'll need an Anthropic
   account with billing set up — the key is the only thing you have to fetch).
2. Click the **Deploy on Railway** button above.
3. When prompted, paste your Anthropic API key and choose a password (the username defaults
   to `admin`). Click deploy.

Railway gives you a URL when it's done — open it, log in, and start adding recipes.

Cost: roughly **$5/month** on Railway's Hobby plan. The Anthropic API is billed separately
on your own account, pay-per-use (a few cents per recipe extraction).

## Run it locally

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

## Configuration

| Variable | Required | Notes |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | yes | used for all Claude extraction features |
| `SECRET_KEY` | yes in production | must be a non-default value when `FLASK_ENV=production` |
| `AUTH_ENABLED` | no (default `true`) | when true, the app requires login |
| `AUTH_USERNAME` / `AUTH_PASSWORD` | yes if auth is enabled | the single login account |
| `FLASK_ENV` | no | `development` (default) or `production` |
| `DATABASE_PATH` | no | SQLite file path; defaults to `/app/data/recipes.db` in the container |
| `HONEYCOMB_API_KEY` | no | enables OpenTelemetry tracing to Honeycomb if set |
| `OTEL_SERVICE_NAME` | no | defaults to `recipe-manager` |
| `HELICONE_ENABLED` / `HELICONE_BASE_URL` / `HELICONE_API_KEY` | no | route Anthropic traffic through a Helicone proxy |

Authentication is a single username/password (set via `AUTH_USERNAME` / `AUTH_PASSWORD`).
There is no multi-user support or external identity provider.

## Database

Recipes are stored in a SQLite file at `/app/data/recipes.db` inside the container (override
with `DATABASE_PATH`). The schema is created automatically on startup. In local dev the
`data/` directory is bind-mounted into the container, so data survives `make down` / `make dev`
cycles; on Railway the same path is backed by a persistent volume.

## Running tests

```bash
make test
```

The suite runs inside Docker. External services are mocked, and each test gets an isolated
SQLite database under a temp directory.

## Self-hosting on your own server

The maintainer runs this on a single VM with Docker Compose behind a Caddy reverse proxy,
with an optional GitHub Actions auto-deploy pipeline. See **[docs/self-hosting.md](docs/self-hosting.md)**.

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
docs/                      # Self-hosting + Railway template guides
```
