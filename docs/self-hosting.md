# Self-hosting on your own server

This is the deployment path used by the maintainer: a single VM running Docker
Compose, with [Caddy](https://caddyserver.com/) in front terminating TLS, and an
optional GitHub Actions pipeline that builds an image and redeploys on every push
to `main`.

If you just want the app running with the least possible effort, use the one-click
[Railway deployment](../README.md) instead — you don't need any of this.

## Prerequisites

- Docker and the Docker Compose plugin (`docker compose`)
- An [Anthropic API key](https://console.anthropic.com/)
- A domain name pointed at the VM (for Caddy / HTTPS)

## Layout on the VM

The production Compose overlay (`compose.prod.yml`) assumes:

- the repo is checked out at `/srv/recipe-manager/app/recipe-manager`
- the SQLite database lives at `/srv/recipe-manager/data` (bind-mounted to `/app/data`)
- the app joins an external Docker network called `web`, shared with Caddy, and does
  **not** publish port `8080` directly

Create the directories:

```bash
sudo install -d -o deploy -g deploy -m 0755 \
  /srv/recipe-manager /srv/recipe-manager/app /srv/recipe-manager/data
```

Clone the repo:

```bash
cd /srv/recipe-manager/app
git clone git@github.com:YOUR_GITHUB_USER/recipe-manager.git
```

## Production `.env`

Create `/srv/recipe-manager/app/recipe-manager/.env`:

```dotenv
ANTHROPIC_API_KEY=your_real_key
SECRET_KEY=a_long_random_secret
FLASK_ENV=production
AUTH_ENABLED=true
AUTH_USERNAME=admin
AUTH_PASSWORD=a_strong_password
# Only needed for the automatic-deploy pipeline below — the GHCR image to pull.
IMAGE_NAME=ghcr.io/your-github-user/recipe-manager
```

Optional Helicone proxy (if you run Helicone as another service on the same network):

```dotenv
HELICONE_ENABLED=true
HELICONE_BASE_URL=http://helicone:8585/v1
HELICONE_API_KEY=optional_helicone_api_key
HELICONE_APP_NAME=recipe-manager
```

Optional Honeycomb tracing:

```dotenv
HONEYCOMB_API_KEY=your_honeycomb_ingest_key
# OTEL_SERVICE_NAME=recipe-manager
```

`DATABASE_PATH` and `PORT` don't need to be set — they default to
`/app/data/recipes.db` and `8080` (in the Dockerfile), and `compose.prod.yml` maps
`/app/data` onto `/srv/recipe-manager/data`.

## Reverse proxy

Create the shared network if it doesn't exist:

```bash
docker network create web
```

Add a Caddy route that proxies to the internal service name:

```caddy
recipes.example.com {
    reverse_proxy recipe-manager:8080
}
```

## Start / update

From the checked-out repo on the VM:

```bash
cd /srv/recipe-manager/app/recipe-manager
docker compose -f compose.yml -f compose.prod.yml pull
docker compose -f compose.yml -f compose.prod.yml up -d
```

Or via the Make targets:

- `make prod-start` — start with the production overlay
- `make prod-stop` — stop the app container without removing it
- `make prod-restart` — restart the app container

## Automatic deploys from GitHub

`.github/workflows/deploy.yml` runs on every push to `main` and:

- runs `make test`
- builds a Docker image
- pushes it to GitHub Container Registry (GHCR), tagged with the commit SHA and `main`
- SSHes into the VM, pulls the image for that commit, and restarts the app with Compose

### 1. Set the image name

In `/srv/recipe-manager/app/recipe-manager/.env`:

```dotenv
IMAGE_NAME=ghcr.io/your-github-user/recipe-manager
```

### 2. Let the VM pull from GHCR

If the package is private, create a GitHub personal access token with at least
`read:packages` and add these repository secrets:

- `GHCR_USERNAME`
- `GHCR_TOKEN`

If the package is public, leave them unset — the VM pulls anonymously.

### 3. Add deployment secrets

Repository secrets for the SSH step:

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY` (private key for a deploy user that can run Docker Compose on the VM)

Optional:

- `DEPLOY_PORT` (if not `22`)

Once those are in place, merges into `main` publish a new image and restart the app
automatically.

### 4. Rollback

Because images are tagged with the commit SHA, roll back by pinning `IMAGE_TAG` on the VM:

```bash
cd /srv/recipe-manager/app/recipe-manager
export IMAGE_TAG=<older-commit-sha>
docker compose -f compose.yml -f compose.prod.yml pull
docker compose -f compose.yml -f compose.prod.yml up -d
```
