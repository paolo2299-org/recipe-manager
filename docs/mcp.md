# MCP server

The app exposes a read-only [Model Context Protocol](https://modelcontextprotocol.io)
endpoint at `/mcp`, so AI tools such as Claude (web, desktop and mobile), Claude
Code, Codex and ChatGPT can search your recipes and read them in full.

Tools:

- `search_recipes` — match title, description, tags and ingredient names; omit
  `query` to list the most recent recipes
- `get_recipe` — full recipe, including ingredients and steps, by id

## Enabling it

Set `MCP_ENABLED=true` in the server's `.env` and restart. In production this
also requires `AUTH_ENABLED=true`, because approving an app relies on the login.
The server must be reachable over HTTPS at a public address for claude.ai and
ChatGPT, since their connectors call it from the vendor's servers.

## How access works

Clients sign in with OAuth 2.1, as the MCP authorization spec describes:

1. The client calls `/mcp`, gets a 401 pointing at
   `/.well-known/oauth-protected-resource/mcp`, and discovers the authorization
   server from there.
2. It registers itself at `/register` (dynamic client registration; open, but
   registrations that are never approved are pruned after a day).
3. It opens `/authorize` in your browser. You sign in if needed and see a
   consent page naming the app; nothing is granted until you click **Allow**.
4. The client exchanges the code (with PKCE) for an access token valid for one
   hour and a refresh token valid for 30 days, rotated on every use.

Tokens only grant the `recipes:read` scope and only work at this server's
`/mcp`. They are stored hashed. The web login session does not grant MCP access.

To see or disconnect apps, sign in and open **Connected Apps**
(`/connected-apps`). Disconnecting takes effect immediately.

## Connecting clients

In these examples `https://recipes.example.com` is your server.

- **claude.ai, Claude Desktop and Claude mobile**: Settings → Connectors →
  Add custom connector, with URL `https://recipes.example.com/mcp`. Connectors
  added on claude.ai are also available on desktop and mobile.
- **Claude Code** (also the Code tab of the Claude desktop app):

  ```bash
  claude mcp add --transport http --scope user recipes https://recipes.example.com/mcp
  ```

  Then run `/mcp` in Claude Code and choose to authenticate.
- **Codex**: add the server to `~/.codex/config.toml`, then run
  `codex mcp login recipes`:

  ```toml
  [mcp_servers.recipes]
  url = "https://recipes.example.com/mcp"
  ```

- **ChatGPT**: add it as a custom connector (developer mode) with the same URL.

## Protocol notes

The server is stateless: each `POST /mcp` carries one JSON-RPC message and gets
one JSON response (no SSE streams or `Mcp-Session-Id`), which works with
multi-worker gunicorn. `GET` and `DELETE` return 405. Requests with a
cross-site `Origin` header are rejected. Client registration accepts `https`
redirect URIs and `http` loopback URIs (any port) only; custom URL schemes are
not supported.
