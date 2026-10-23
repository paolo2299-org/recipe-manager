"""JSON-RPC message handling for a stateless MCP Streamable HTTP server.

Only the parts of the protocol a tools-only server needs are implemented:
initialize, ping, tools/list and tools/call. Every POST is answered with a
single JSON body (no SSE stream), and no session state is kept between
requests, which keeps the endpoint compatible with multi-worker gunicorn.
"""

from typing import Any

from .tools import HANDLERS, TOOLS, call_tool

SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

SERVER_INFO = {"name": "recipe-manager", "title": "Recipe Manager", "version": "0.1.0"}
INSTRUCTIONS = (
    "Read-only access to a personal recipe collection. Use search_recipes to find "
    "recipes, then get_recipe for full ingredients and steps."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _initialize(params: dict[str, Any]) -> dict[str, Any]:
    requested = params.get("protocolVersion")
    version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
        "instructions": INSTRUCTIONS,
    }


def handle_message(message: Any) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. Returns None when no reply is due."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return error_response(None, INVALID_REQUEST, "Expected a JSON-RPC 2.0 object")

    method = message.get("method")
    if "id" not in message:
        # Notifications (e.g. notifications/initialized) and client responses
        # need no reply.
        return None

    request_id = message["id"]
    if not isinstance(method, str):
        return error_response(request_id, INVALID_REQUEST, "Missing method")

    params = message.get("params") or {}
    if not isinstance(params, dict):
        return error_response(request_id, INVALID_PARAMS, "params must be an object")

    if method == "initialize":
        return _result(request_id, _initialize(params))
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in HANDLERS:
            return error_response(request_id, INVALID_PARAMS, f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            return error_response(request_id, INVALID_PARAMS, "arguments must be an object")
        return _result(request_id, call_tool(name, arguments))

    return error_response(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
