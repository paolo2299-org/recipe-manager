# MCP server

The app exposes a read-only [Model Context Protocol](https://modelcontextprotocol.io)
endpoint at `/mcp`, so AI tools such as Claude Code, Claude Desktop and Codex can
search your recipes and read them in full.

Tools:

- `search_recipes` — match title, description, tags and ingredient names; omit
  `query` to list the most recent recipes
- `get_recipe` — full recipe, including ingredients and steps, by id

## Enabling it

The endpoint is off until `MCP_TOKEN` is set. Generate a token of at least 32
characters and add it to the server's `.env`:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Clients send it as `Authorization: Bearer <token>`. It is separate from the web
login: a browser session does not grant MCP access, and the token does not grant
access to the web UI. Anyone holding the token can read every recipe, so treat it
like a password and only use it over HTTPS. To revoke it, change `MCP_TOKEN` and
restart the app.

## Connecting clients

In the examples below, `RECIPES_MCP_TOKEN` is an environment variable holding the
token on the client machine, and `https://recipes.example.com` is your server.

Claude Code (also used by the Code tab of the Claude desktop app):

```bash
claude mcp add --transport http --scope user recipes https://recipes.example.com/mcp --header "Authorization: Bearer $RECIPES_MCP_TOKEN"
```

Codex, in `~/.codex/config.toml`:

```toml
[mcp_servers.recipes]
url = "https://recipes.example.com/mcp"
bearer_token_env_var = "RECIPES_MCP_TOKEN"
```

Claude Desktop chat cannot attach a fixed header to a custom connector, so use
the `mcp-remote` bridge in `claude_desktop_config.json` instead:

```json
{
  "mcpServers": {
    "recipes": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://recipes.example.com/mcp",
               "--header", "Authorization: Bearer ${RECIPES_MCP_TOKEN}"],
      "env": {"RECIPES_MCP_TOKEN": "<token>"}
    }
  }
}
```

claude.ai, the Claude mobile apps and ChatGPT connectors require OAuth and are
not supported by this endpoint.

## Protocol notes

The server is stateless: each `POST /mcp` carries one JSON-RPC message and gets
one JSON response (no SSE streams or `Mcp-Session-Id`), which works with
multi-worker gunicorn. `GET` and `DELETE` return 405. Requests with a
cross-site `Origin` header are rejected.
