"""Tests for the transport-independent MCP message handling and tools."""

from app.mcp.protocol import LATEST_PROTOCOL_VERSION, handle_message
from app.storage.recipes import save_recipe
from tests.conftest import make_recipe


def rpc(method, params=None, request_id=1):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return handle_message(message)


def test_initialize_echoes_supported_version(app):
    with app.app_context():
        result = rpc("initialize", {"protocolVersion": "2025-06-18"})["result"]

    assert result["protocolVersion"] == "2025-06-18"
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    assert result["serverInfo"]["name"] == "recipe-manager"


def test_initialize_offers_latest_for_unknown_version(app):
    with app.app_context():
        result = rpc("initialize", {"protocolVersion": "1999-01-01"})["result"]

    assert result["protocolVersion"] == LATEST_PROTOCOL_VERSION


def test_notifications_get_no_reply(app):
    with app.app_context():
        assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_and_bad_messages(app):
    with app.app_context():
        assert rpc("resources/list")["error"]["code"] == -32601
        assert handle_message([])["error"]["code"] == -32600
        assert rpc("tools/call", {"name": "nope"})["error"]["code"] == -32602


def test_tools_list_names(app):
    with app.app_context():
        tools = rpc("tools/list")["result"]["tools"]

    assert [t["name"] for t in tools] == ["search_recipes", "get_recipe"]


def test_search_and_get_recipe(app):
    with app.app_context():
        cookies_id = save_recipe(make_recipe(), "url", "https://example.com/cookies")
        save_recipe(make_recipe(title="Thai Curry", description="Fragrant curry.", tags=["Thai"]), "url", "https://example.com/curry")

        all_results = rpc("tools/call", {"name": "search_recipes", "arguments": {}})["result"]
        cookies = rpc(
            "tools/call", {"name": "search_recipes", "arguments": {"query": "COOKIES"}}
        )["result"]
        thai = rpc("tools/call", {"name": "search_recipes", "arguments": {"query": "thai"}})["result"]
        detail = rpc("tools/call", {"name": "get_recipe", "arguments": {"id": cookies_id}})["result"]

    assert len(all_results["structuredContent"]["recipes"]) == 2
    assert [r["title"] for r in cookies["structuredContent"]["recipes"]] == ["Test Cookies"]
    assert [r["title"] for r in thai["structuredContent"]["recipes"]] == ["Thai Curry"]
    assert detail["isError"] is False
    assert detail["structuredContent"]["ingredients"][0]["name"] == "flour"
    assert '"Test Cookies"' in detail["content"][0]["text"]


def test_tool_errors_are_reported_to_the_model(app):
    with app.app_context():
        missing = rpc("tools/call", {"name": "get_recipe", "arguments": {"id": "999"}})["result"]
        bad_limit = rpc(
            "tools/call", {"name": "search_recipes", "arguments": {"limit": 0}}
        )["result"]

    assert missing["isError"] is True
    assert "999" in missing["content"][0]["text"]
    assert bad_limit["isError"] is True
