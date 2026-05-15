# Configuration reference

## Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | yes | used for all Claude extraction features |
| `SECRET_KEY` | yes in production | must be a non-default value when `FLASK_ENV=production` |
| `AUTH_ENABLED` | no (default `true`) | when true, the app requires login |
| `AUTH_USERNAME` / `AUTH_PASSWORD` | yes if auth is enabled | the single login account |
| `FLASK_ENV` | no | `development` (default) or `production` |
| `DATABASE_PATH` | no | SQLite file path; defaults to `/app/data/recipes.db` in the container |
| `HELICONE_ENABLED` / `HELICONE_BASE_URL` / `HELICONE_API_KEY` | no | route Anthropic traffic through a Helicone proxy |

Authentication is a single username/password (set via `AUTH_USERNAME` / `AUTH_PASSWORD`).
There is no multi-user support or external identity provider.

## Database

Recipes are stored in a SQLite file at `/app/data/recipes.db` inside the container (override
with `DATABASE_PATH`). The schema is created automatically on startup. In local dev the
`data/` directory is bind-mounted into the container, so data survives `make down` / `make dev`
cycles; on Railway the same path is backed by a persistent volume.
