# Publishing the Railway template (maintainer notes)

The "Deploy on Railway" button in the README points at a published Railway
*template*. The template can't live in this repo — it's created once on
[railway.app](https://railway.app) and references this repo. The repo side
(`railway.toml`, the `/health` endpoint, the `DATABASE_PATH` default in the
Dockerfile) is already in place; this doc covers the ~10-minute one-time setup.

## 1. Create the project

On Railway: **New Project → Deploy from GitHub repo →** pick this repo. Railway
detects the `Dockerfile` / `railway.toml` and builds from it.

## 2. Add a volume

Add a **Volume** to the service, mounted at:

```
/app/data
```

This is where the SQLite database lives. Without it, recipes are wiped on every
redeploy. Keep the service at **1 replica** (the default) — SQLite on one volume
must not be written by more than one instance; `railway.toml` already pins
`numReplicas = 1`.

## 3. Set service variables

| Variable | Value | Notes |
| --- | --- | --- |
| `FLASK_ENV` | `production` | enables prod config + secure cookies |
| `SECRET_KEY` | `${{secret(48)}}` | Railway's secret generator — auto-filled, never shown to the user |
| `AUTH_ENABLED` | `true` | |
| `AUTH_USERNAME` | `admin` | sensible default; user can change it |
| `AUTH_PASSWORD` | *(leave empty, mark required)* | the user picks this at deploy time |
| `ANTHROPIC_API_KEY` | *(leave empty, mark required)* | the user pastes their key at deploy time |

Do **not** set `PORT` (Railway injects it) or `DATABASE_PATH` (defaults to the
mounted volume path).

Optional, only if you want them exposed: `HONEYCOMB_API_KEY`, `HELICONE_ENABLED`
+ `HELICONE_BASE_URL` + `HELICONE_API_KEY`. Leave them out for the simplest flow.

## 4. Publish the template

Project settings → **Create Template**. Fill in:

- name + description
- for `AUTH_PASSWORD` and `ANTHROPIC_API_KEY`: a clear label and help text (e.g.
  "Your Anthropic API key — get one at https://console.anthropic.com/")
- mark `AUTH_PASSWORD` and `ANTHROPIC_API_KEY` as required user input; leave the
  rest as-is

Publish, then copy the `https://railway.app/template/XXXXXX` URL into the README
button (replace the `XXXXXX` placeholder).

## 5. Smoke test

Deploy the template into a throwaway project and confirm:

- it builds and boots; `/health` returns `200`
- the public URL serves HTTPS and login works with the password you chose
- add a recipe, trigger a redeploy, and confirm the recipe survives (volume works)
