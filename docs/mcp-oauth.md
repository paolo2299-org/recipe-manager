# MCP authentication: decision record and OAuth plan

Status: the [MCP server](mcp.md) uses a static bearer token (`MCP_TOKEN`).
OAuth is deferred. If we add it, the preferred implementation is the
Authlib-based prototype on branch `codex/mcp-oauth-authlib`.

## Why MCP needs its own authentication

The web app's login is a username/password form that sets a session cookie.
MCP clients cannot fill in a form or keep a cookie, so `/mcp` is exempt from
the session guard and authenticates each request with an
`Authorization: Bearer` header instead.

## Options considered

Three prototypes were built on the same shared MCP core (commit `e780d85`), so
their branches differ only in authentication:

| | Static bearer token | Hand-written OAuth | Authlib OAuth |
|---|---|---|---|
| Branch | `codex/mcp-bearer` (adopted) | `codex/mcp-oauth` | `codex/mcp-oauth-authlib` (preferred if we add OAuth) |
| App code added | ~90 lines | ~900 lines | ~960 lines |
| Claude Code, Codex (CLI, IDE, desktop app) | yes | yes | yes |
| Claude Desktop chat | via the `mcp-remote` bridge | yes, as a custom connector | yes, as a custom connector |
| claude.ai, Claude mobile, ChatGPT | no | yes | yes |
| Revoking access | change `MCP_TOKEN` and restart | Connected Apps page | Connected Apps page |
| New dependencies | none | none | `authlib` |

A local stdio server, for example `ssh <vps> docker exec -i ... python -m app.mcp`,
was also considered. It needs no new authentication but only suits clients that
can launch a local command.

## Why the bearer token for now

- The clients in use (Claude Code and Codex, including the Codex desktop app)
  all support a fixed bearer token.
- It is about 90 lines with no new dependencies, tables or pages.
- As of October 2026, an open Codex issue reported the desktop app
  authenticating to an OAuth MCP server but never loading its tools
  ([openai/codex#20009](https://github.com/openai/codex/issues/20009)), so a
  static token was the more reliable path there.

The trade-offs we accepted: a single shared secret with no per-client
revocation, and no access from claude.ai, Claude mobile or ChatGPT. Those
connectors call the server from the vendor's infrastructure and only support
OAuth (or no authentication at all).

## When to revisit

Add OAuth when any of these become true:

- We want recipes available in claude.ai, the Claude mobile apps or ChatGPT.
- More than one person or device needs access and we want to revoke them
  individually.
- We add MCP tools that change data or call the Anthropic API, where a leaked
  shared token would cost more.

## The OAuth design (MCP authorization spec)

Both OAuth prototypes implement the same behaviour, covered by the same 27 tests
in `tests/test_mcp_oauth.py`:

1. An unauthenticated `POST /mcp` gets a 401 whose `WWW-Authenticate` header
   points at `/.well-known/oauth-protected-resource/mcp` (RFC 9728). That
   document names the app itself as the authorization server, described at
   `/.well-known/oauth-authorization-server` (RFC 8414).
2. Clients register themselves at `/register` (RFC 7591). Registration is open,
   as MCP clients expect. Registrations that are never approved are pruned after
   a day, and the total is capped.
3. The client opens `/authorize` in the browser. That route stays behind the
   existing login guard, so the signed-in owner sees a consent page naming the
   client and its redirect host. The page is protected against forged form posts
   and framing. Nothing is granted until **Allow** is clicked.
4. `/token` exchanges the code with PKCE (S256 only, required for every
   client). It issues a one-hour access token and a 30-day refresh token that
   rotates on every use. `/revoke` supports RFC 7009.
5. Tokens carry only the `recipes:read` scope and are bound to this server's
   `/mcp` (RFC 8707 `resource`). The RFC 9207 `iss` parameter is added to
   authorization redirects.
6. A **Connected Apps** page lists active grants and disconnects them
   immediately.

Other details:

- Redirect URIs must be `https` or `http` loopback. Loopback redirects may use
  any port (RFC 8252), which Claude Code and Codex rely on.
- Client secrets, codes and tokens are stored only as SHA-256 hashes, in three
  SQLite tables.
- `MCP_ENABLED=true` turns it on. In production it requires `AUTH_ENABLED`,
  because the consent step relies on the login.

## Preferred implementation: Authlib

Authlib provides the parts that are easiest to get subtly wrong:

- the authorization code grant and redirect validation
- PKCE
- client authentication (`none`, `client_secret_post`, `client_secret_basic`)
- refresh token rotation
- revocation
- registration metadata validation
- the `iss` parameter
- bearer token checks on `/mcp`

We keep only what Authlib does not cover:

- the discovery documents
- resource binding (RFC 8707)
- loopback-port matching and the stricter redirect URI rules
- the SQLite models
- the consent and Connected Apps pages
- registration limits

The code is not shorter than the hand-written version, at roughly the same size.
The reason to prefer it is that the security-sensitive logic comes from a widely
used, maintained library, and fixes arrive by upgrading.

Decisions to keep if we pick this up:

- **Keep the custom SQLite models; don't adopt SQLAlchemy.** Authlib's
  SQLAlchemy mixins would save about 200–250 lines. However, they store client
  secrets and tokens in plain text, never expire refresh tokens and match
  redirect URIs exactly. Restoring those properties means overriding most of
  them. Moving recipe and calorie storage to SQLAlchemy only for this isn't
  worth the churn.
- Authlib refuses OAuth over plain HTTP except on loopback addresses. In
  production, `ProxyFix` makes requests behind Caddy appear as HTTPS. In
  development, sign-in only works on `DEV_HOST=127.0.0.1`, not over a Tailscale
  `http://` URL.
- Two places deliberately diverge from Authlib's defaults:
  - Public clients get no `client_secret` field in the registration response.
  - Bad redirect URIs return `invalid_redirect_uri` rather than
    `invalid_client_metadata`.

## Picking it up later

The prototype branches are kept on GitHub. To revive the Authlib version:

1. Rebase `codex/mcp-oauth-authlib` onto `main`, or cherry-pick its last
   commit. Its base is the same MCP core this branch already contains.
2. Decide whether to keep `MCP_TOKEN` alongside OAuth. The prototype replaces
   it. Keeping both would let existing Claude Code and Codex setups work
   unchanged while OAuth-only connectors are added.
3. Check `requirements.txt` for `authlib` and update to a current version.
   The prototype was built against Authlib 1.9.1.
4. Re-check the current MCP authorization spec. In particular, the 2025-11-25
   revision prefers Client ID Metadata Documents over dynamic registration, and
   the prototype only implements dynamic registration.
5. Run `make test` and `make typecheck`. Then repeat the end-to-end check with
   the official MCP Python SDK's `OAuthClientProvider` against a dev server
   started with `AUTH_ENABLED=true MCP_ENABLED=true DEV_HOST=127.0.0.1`.
