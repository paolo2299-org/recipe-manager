# Configuration reference

## Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | yes | used for all Claude extraction features |
| `SECRET_KEY` | yes in production | must be a non-default value when `FLASK_ENV=production` |
| `AUTH_ENABLED` | no (default `true`) | when true, the app requires login |
| `AUTH_USERNAME` / `AUTH_PASSWORD` | yes if auth is enabled | the single login account |
| `FLASK_ENV` | no | `development` (default) or `production` |
| `DATABASE_PATH` | no | SQLite file path; native `make dev` forces `.dev/recipes.db`, while the container defaults to `/app/data/recipes.db` |

Authentication is a single username/password (set via `AUTH_USERNAME` / `AUTH_PASSWORD`).
There is no multi-user support or external identity provider.

## Database

The schema is created automatically on startup. Native development stores
recipes in each worktree's ignored `.dev/recipes.db`. Production containers use
`/app/data/recipes.db`, backed by a persistent host directory.
