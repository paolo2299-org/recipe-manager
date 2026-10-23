"""Tests for the bearer-token protected /mcp endpoint."""

import pytest

from app import create_app, validate_mcp_config

TOKEN = "t" * 40
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test"}},
}


@pytest.fixture
def mcp_app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "mcp-test-secret",
            "AUTH_ENABLED": True,
            "AUTH_USERNAME": "chef",
            "AUTH_PASSWORD": "secret",
            "MCP_TOKEN": TOKEN,
            "DATABASE_PATH": str(tmp_path / "mcp-test.db"),
        }
    )


@pytest.fixture
def mcp_client(mcp_app):
    return mcp_app.test_client()


def auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_disabled_without_token(client):
    assert client.post("/mcp", json=INIT, headers=auth()).status_code == 404


def test_missing_or_wrong_token_is_rejected(mcp_client):
    missing = mcp_client.post("/mcp", json=INIT)
    wrong = mcp_client.post("/mcp", json=INIT, headers=auth("x" * 40))

    assert missing.status_code == 401
    assert missing.headers["WWW-Authenticate"].startswith("Bearer")
    assert wrong.status_code == 401


def test_login_session_does_not_grant_mcp_access(mcp_client):
    mcp_client.post("/login", data={"username": "chef", "password": "secret"})

    assert mcp_client.post("/mcp", json=INIT).status_code == 401


def test_valid_token_bypasses_login_redirect(mcp_client):
    response = mcp_client.post("/mcp", json=INIT, headers=auth())

    assert response.status_code == 200
    assert response.get_json()["result"]["protocolVersion"] == "2025-06-18"


def test_notification_returns_accepted(mcp_client):
    response = mcp_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=auth(),
    )

    assert response.status_code == 202
    assert response.data == b""


def test_tools_call_round_trip(mcp_client):
    response = mcp_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "search_recipes", "arguments": {}}},
        headers={**auth(), "MCP-Protocol-Version": "2025-06-18"},
    )

    assert response.status_code == 200
    assert response.get_json()["result"]["structuredContent"] == {"recipes": []}


def test_bad_requests(mcp_client):
    bad_json = mcp_client.post(
        "/mcp", data="{", content_type="application/json", headers=auth()
    )
    bad_version = mcp_client.post(
        "/mcp", json=INIT, headers={**auth(), "MCP-Protocol-Version": "1999-01-01"}
    )
    cross_origin = mcp_client.post(
        "/mcp", json=INIT, headers={**auth(), "Origin": "https://evil.example"}
    )

    assert bad_json.status_code == 400
    assert bad_json.get_json()["error"]["code"] == -32700
    assert bad_version.status_code == 400
    assert cross_origin.status_code == 403


def test_get_is_not_allowed(mcp_client):
    response = mcp_client.get("/mcp", headers=auth())

    assert response.status_code == 405
    assert response.headers["Allow"] == "POST"


def test_short_token_rejected_at_startup(app):
    app.config.update(TESTING=False, MCP_TOKEN="short")

    with pytest.raises(RuntimeError, match="MCP_TOKEN"):
        validate_mcp_config(app)
