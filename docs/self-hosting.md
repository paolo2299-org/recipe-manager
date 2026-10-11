# Self-hosting on your own server

This is the deployment path used by the maintainer: a single VM running Docker
Compose, with [Caddy](https://caddyserver.com/) in front terminating TLS, and an
optional GitHub Actions pipeline that builds and publishes an image on every push
to `main`. The VM pulls published images independently; GitHub Actions does not
connect to it.

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
# Only needed when pulling the published GHCR image.
IMAGE_NAME=ghcr.io/your-github-user/recipe-manager
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

## Publishing images from GitHub

`.github/workflows/deploy.yml` runs on every push to `main` and:

- runs `make test`
- builds a Docker image
- pushes it to GitHub Container Registry (GHCR), tagged with the commit SHA and `main`

The workflow stops after publishing the image. It has no SSH access to the VM and
does not initiate a production deployment.

### 1. Set the image name

In `/srv/recipe-manager/app/recipe-manager/.env`:

```dotenv
IMAGE_NAME=ghcr.io/your-github-user/recipe-manager
```

### 2. Let the VM pull from GHCR

If the package is private, create a GitHub personal access token with at least
`read:packages`. Store the credentials on the VM for the pull-based deployment
service; do not add them to this repository's Actions secrets.

If the package is public, leave them unset — the VM pulls anonymously.

### 3. Rollback

Because images are tagged with the commit SHA, roll back by pinning `IMAGE_TAG` on the VM:

```bash
cd /srv/recipe-manager/app/recipe-manager
export IMAGE_TAG=<older-commit-sha>
docker compose -f compose.yml -f compose.prod.yml pull
docker compose -f compose.yml -f compose.prod.yml up -d
```
