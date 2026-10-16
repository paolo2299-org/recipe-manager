# Recipe Manager

An AI-powered web app for saving and managing all of your recipes in one place, with zero effort.

## Deploy on Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.com/deploy/kqrBFL)

1. Get an [Anthropic API key](https://console.anthropic.com/)
2. Click the button above
3. Paste your API key and choose a password when prompted. Click deploy

Railway gives you a URL when it's done — open it, log in, and start adding recipes.

Cost: **free** on Railway's free tier, plus a few cents per recipe extraction billed to your Anthropic account.

## More documentation

- Development and tests use Python 3.12 with uv; CI runs the same commands.
  Docker is used for production images and deployment.
- For parallel tasks, use `make worktree-create NAME=<task-name>` from a clean
  retained checkout. When finished testing, run `make worktree-finish NAME=<task-name>`
  from the retained checkout: it checks for unfinished/unpublished work, stops the
  server and removes disposable files/worktree while retaining the branch.
  Unexpected ignored files such as `.env` block cleanup. See the lifecycle guide below.
- For a worktree-local native development server, run `make setup` and then
  `make dev-start`. The server prints its allocated local or Tailscale URL;
  `make dev-stop` stops it. Use `make dev` for a foreground terminal session.
- [Local development](docs/local-development.md) — running the app locally, make commands, and tests
- [Configuration reference](docs/configuration.md) — all environment variables and database settings
- [Self-hosting on your own server](docs/self-hosting.md) — Docker Compose + Caddy setup on a VM
- [Publishing the Railway template](docs/railway-template.md) — maintainer notes for the one-click deploy button

Private native-development settings can be shared across worktrees without
committing secrets: see [private development configuration](docs/local-development.md#private-configuration-shared-by-worktrees).
Use `make dev-config` to validate the project's host config without printing values.
