# Recipe Manager

A web application for extracting and saving structured recipe data from photos, URLs, and pasted text using the Claude API.

## Deploy on Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.com/deploy/kqrBFL)

1. Get an [Anthropic API key](https://console.anthropic.com/) — this is the only thing you need to fetch.
2. Click the button above.
3. Paste your API key and choose a password when prompted. Click deploy.

Railway gives you a URL when it's done — open it, log in, and start adding recipes.

Cost: **free** on Railway's free tier, plus a few cents per recipe extraction billed to your Anthropic account.

## More documentation

- [Local development](docs/local-development.md) — running the app locally, make commands, and tests
- [Configuration reference](docs/configuration.md) — all environment variables and database settings
- [Self-hosting on your own server](docs/self-hosting.md) — Docker Compose + Caddy setup on a VM
- [Publishing the Railway template](docs/railway-template.md) — maintainer notes for the one-click deploy button
