---
name: dev-app
description: Run, restart, stop, or clean up the Recipe Manager development app in this repository and its worktrees. Use for "please run the app", "start the dev server", "show me the app", "stop the app", "clean up this environment", or "I'm finished testing". Uses this project's native development commands; excludes other repositories, production deployments and unrelated cleanup.
---

# Run and finish Recipe Manager

Use the project's existing Make targets. Choose environment names and handle
setup yourself; the user should not need to specify commands, ports or paths.

## Resolve the project and environment

- Apply this skill only to the repository containing this SKILL.md and that
  repository's Git worktrees. Resolve its root from the skill's location and
  Git metadata, rather than assuming the current directory is the right app.
  If the user means a different project, use that project's own instructions;
  do not impose this workflow on it.
- Read the selected project's `AGENTS.md` and consult
  `docs/local-development.md` for app-specific details. Check Git status and the
  current worktree before running anything.
- Reuse this task's current worktree, including uncommitted code, when one is
  already selected. Reuse the environment this chat previously created instead
  of making a new one on every turn. Do not select another chat's environment
  simply because it is running or appears newest in `make worktree-list`.
- Otherwise, from a clean retained checkout, run
  `make worktree-create NAME=<name>`. Choose a unique lowercase name yourself,
  such as `dev-20261015-103015-a4f2`, unless the user specifies one. Use the
  printed path and retain the controller checkout path for later cleanup.
- A new worktree contains committed code only. If a dirty retained checkout is
  the intended source, do not silently run an older commit, stash, commit, or
  copy changes. Explain the obstruction and resolve which code to run with the
  user. If the required Make targets are absent, report that rather than
  inventing a second development workflow.

## Run, show, or restart the app

1. In the selected worktree, run `make setup`, then `make dev-start`. For an
   explicit restart after code changes, use `make dev-stop` followed by
   `make dev-start`; otherwise an existing server may be reused. Use the
   detached target so the server survives this turn and phone disconnects.
2. Read `make dev-status` or `.dev/session.json` for the real URL and named
   Playwright session. Verify HTTP readiness with GET `/health`.
   Do not load a large model
   or run the entire test suite merely to launch a preview unless the repository
   instructions require it.
3. Return the clickable URL and concise environment details required by the
   repository guide. Mention any login or missing assets noted below that limit
   the preview. Keep the server
   available until the user asks to stop or finish it.

## Project details

Recipe Manager always uses this worktree's `.dev/recipes.db`. Do not copy a
production database or `.env`; without a development `.env`, auth is disabled
and extraction requiring Anthropic credentials is unavailable.

Do not copy production `.env` files or credentials.
Use the allocated loopback/Tailscale address. Ordinary previews do not need
production Compose, Caddy changes, a deployment, commits or pushes. If a command
needs sandbox/network permission, use the normal approval mechanism rather than
disabling protections. Check `.dev/server.log` if startup fails.

## Stop versus finish

- **"Stop the app"** means `make dev-stop` in this chat's environment. Keep its
  worktree and data so the user can resume.
- **"Clean up this environment", "I'm finished testing", or "finish this
  environment"** means finish the identified development environment. Generic
  "clean up" without an app-testing context is not permission to delete other
  worktrees, branches or project files.

For finishing, use the environment name/path recorded in this chat or the
currently selected managed worktree. `make worktree-list` can verify the mapping.
If ownership is unclear or several environments could match, ask which one;
never guess from age or remove all environments.

Close only this environment's named Playwright session if one was opened.
From its retained controller checkout, run
`make worktree-check NAME=<name>` and, if it passes,
`make worktree-finish NAME=<name>`. The finish command repeats the safety checks,
stops that server, removes disposable files and its worktree, and retains the
branch. The user's clear request to finish authorizes this ordinary guarded
cleanup; no extra confirmation is needed when the target is unambiguous.

Respect refusals for unfinished files, unpublished commits, unexpected ignored
files or unavailable remote checks. Explain what remains and leave it in place.
Do not force removal, delete branches, or commit/push just to bypass a guard.
For a manually or app-created worktree the helper does not manage, stop only
the identified server and report that its worktree is retained. Do not adopt or
remove it automatically. Report the removed environment and retained branch
after successful cleanup. A turn ending alone is never a cleanup signal.
