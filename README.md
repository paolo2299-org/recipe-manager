# Recipe Manager

A web application for extracting and saving structured recipe data from photos and URLs using Claude's vision and tool use APIs.

## Overview

Upload a photo of a recipe or paste a URL, and the app uses Claude to extract structured information — title, ingredients, steps, timings, and tags. Recipes are saved to a local SQLite database and can be browsed, viewed, and deleted.

Built with Flask, HTMX, Pico CSS, SQLite, and Google OpenID Connect. Intended for self-hosted deployment.

## Prerequisites

- Docker
- Docker Compose (`docker compose`)
- An [Anthropic API key](https://console.anthropic.com/)
- A Google OAuth web client for sign-in

## Setup

### 1. Clone and configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```
ANTHROPIC_API_KEY=your_key_here
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret
GOOGLE_ALLOWED_EMAILS=chef@example.com
SECRET_KEY=change-me-in-production
```

Set `GOOGLE_ALLOWED_EMAILS` to a comma-separated list of the exact Google account emails that should have access.

### 2. Create a Google OAuth client

Create a Google OAuth 2.0 Web application client in Google Cloud and add this authorized redirect URI for local dev:

- `http://localhost:8080/auth/google/callback`

The app uses Google OpenID Connect for sign-in and only allows emails listed in `GOOGLE_ALLOWED_EMAILS`.

## Database

Recipes are stored in a SQLite file at `data/recipes.db` by default. Under Docker Compose, the app is configured to use `/app/data/recipes.db` inside the container so both local and production mounts land in the same place. The schema is created automatically on startup. In local dev the `data/` directory is bind-mounted into the container, so data survives `make down` / `make dev` cycles.

To use a different path, set `DATABASE_PATH` in your `.env`.

## Running locally

```bash
make dev
```

The app is available at `http://localhost:8080` with Flask hot reload enabled.

Useful local commands:

- `make dev` starts the app.
- `make test` runs the pytest suite inside Docker.
- `make shell` opens a shell inside the running app container.
- `make down` stops and removes the local containers.

If `.env` is not present yet, the `make` targets automatically fall back to `.env.example` so teardown and config validation still work in a fresh checkout. To actually run the app against real credentials, copy `.env.example` to `.env` and fill in the secrets.

Under the hood, local development uses:

```bash
docker compose -f compose.yml -f compose.dev.yml up
```

## Running tests

```bash
make test
```

The test suite runs inside Docker. External services are mocked, and each test gets an isolated SQLite database under a temp directory.

## Production on a VM

The production Compose overlay is designed for a single-VM setup where only Caddy publishes public ports and the Flask app stays private on a shared Docker network.

Install Docker and the Compose plugin on the VM, then create the app and data directories:

```bash
sudo install -d -o deploy -g deploy -m 0755 /srv/recipe-manager /srv/recipe-manager/app /srv/recipe-manager/data
```

Clone this repo onto the VM so the Compose files live at `/srv/recipe-manager/app`:

```bash
cd /srv/recipe-manager/app
git clone git@github.com:YOUR_GITHUB_USER/recipe-organizer.git .
```

Create a production `.env` file at `/srv/recipe-manager/app/.env` with your real secrets:

```dotenv
ANTHROPIC_API_KEY=your_real_key
SECRET_KEY=a_long_random_secret
FLASK_ENV=production
GOOGLE_AUTH_ENABLED=true
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_ALLOWED_EMAILS=chef@example.com
IMAGE_NAME=ghcr.io/your-github-user/your-repo-name
```

Create the shared Docker network if it does not already exist:

```bash
docker network create web
```

The production service joins the external Docker network `web`, stores SQLite data under `/srv/recipe-manager/data`, and does not publish port `8080` directly.

Add a Caddy route that proxies to the internal service name:

```caddy
recipes.example.com {
	reverse_proxy recipe-manager:8080
}
```

To start or manually update the production stack from the checked-out repo on the VM:

```bash
cd /srv/recipe-manager/app
docker compose -f compose.yml -f compose.prod.yml pull
docker compose -f compose.yml -f compose.prod.yml up -d
```

If you prefer using the Make targets from the checked-out repo, the production helpers are:

- `make prod-start` starts the app with the production Compose overlay.
- `make prod-stop` stops the production app container without removing it.
- `make prod-restart` restarts the production app container.

### Automatic deploys from GitHub to a VM

This repo includes a GitHub Actions workflow at `.github/workflows/deploy.yml` that:

- runs `make test`
- builds a Docker image
- pushes it to GitHub Container Registry (GHCR)
- SSHes into your production VM
- pulls the exact image for the merged commit
- restarts the app with Docker Compose

The workflow triggers on pushes to `main`, which means merges into `main` deploy automatically.

Assuming the VM is already set up as described above, these are the extra steps for automatic deployment.

#### 1. Set the image name

Set `IMAGE_NAME` in `/srv/recipe-manager/app/.env` so Compose pulls the correct GHCR image:

```dotenv
IMAGE_NAME=ghcr.io/your-github-user/your-repo-name
```

#### 2. Give the VM permission to pull from GHCR

If the repository or package is private, create a GitHub personal access token with at least `read:packages`. Add these repository secrets in GitHub:

- `GHCR_USERNAME`
- `GHCR_TOKEN`

If the package is public, you can leave those two secrets unset and the VM can pull anonymously.

#### 3. Add deployment secrets to GitHub

Add these repository secrets for the SSH step:

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`

Optional:

- `DEPLOY_PORT` if you do not use port `22`

The SSH key should be the private key for a deploy user that can run Docker Compose on the VM.

#### 4. Enable the workflow

After those secrets are in place, merges into `main` will publish a new image and restart the app automatically.

#### 5. Rollback

Because the workflow deploys the image tagged with the Git commit SHA, rollback is simple: set `IMAGE_TAG` to an older commit SHA on the VM and rerun Compose.

```bash
cd /srv/recipe-manager/app
export IMAGE_TAG=<older-commit-sha>
docker compose -f compose.yml -f compose.prod.yml pull
docker compose -f compose.yml -f compose.prod.yml up -d
```

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
  storage/
    db.py                  # SQLite connection + schema init
    recipes.py             # Recipe CRUD operations
  routes/
    auth.py                # Google OAuth routes and auth gate
    recipes.py             # Flask blueprint with all routes
  templates/               # Jinja2 templates (Pico CSS + HTMX)
  static/css/app.css       # Minimal custom styles
data/                      # SQLite database lives here (bind-mounted)
tests/                     # Pytest suite
exploration/               # Original CLI extraction scripts (reference)
compose.yml                # Shared Compose settings
compose.dev.yml            # Local development + test overrides
compose.prod.yml           # Production VM overrides
```

## Exploration scripts

The original CLI scripts are preserved in `exploration/` for reference. See `exploration/requirements.txt` for their dependencies.

```bash
# Extract from URL
python exploration/extract_anthropic.py https://example.com/my-recipe

# Extract from image
python exploration/extract_image_anthropic.py recipe.jpg
```
