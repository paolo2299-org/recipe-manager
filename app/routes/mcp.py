"""MCP Streamable HTTP endpoint, protected by a static bearer token."""

import hmac
import json
from urllib.parse import urlsplit

from flask import Blueprint, Response, abort, current_app, jsonify, request

from app.mcp.protocol import (
    INVALID_REQUEST,
    PARSE_ERROR,
    SUPPORTED_PROTOCOL_VERSIONS,
    error_response,
    handle_message,
)

bp = Blueprint("mcp", __name__)


def _unauthorized() -> Response:
    response = jsonify(error="invalid_token")
    response.status_code = 401
    response.headers["WWW-Authenticate"] = 'Bearer realm="recipe-manager"'
    return response


@bp.before_request
def require_token() -> Response | None:
    expected = current_app.config.get("MCP_TOKEN", "")
    if not expected:
        abort(404)

    # Reject cross-site browser requests (DNS rebinding protection).
    origin = request.headers.get("Origin")
    if origin and urlsplit(origin).netloc != request.host:
        abort(403)

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        token.strip().encode(), expected.encode()
    ):
        return _unauthorized()
    return None


@bp.route("/mcp", methods=["POST"])
def endpoint() -> Response | tuple[Response, int] | tuple[str, int]:
    version = request.headers.get("MCP-Protocol-Version")
    if version and version not in SUPPORTED_PROTOCOL_VERSIONS:
        return jsonify(error_response(None, INVALID_REQUEST, "Unsupported MCP-Protocol-Version")), 400

    try:
        message = json.loads(request.get_data(as_text=True))
    except ValueError:
        return jsonify(error_response(None, PARSE_ERROR, "Invalid JSON")), 400

    reply = handle_message(message)
    if reply is None:
        return "", 202
    return jsonify(reply)


@bp.route("/mcp", methods=["GET", "DELETE"])
def not_allowed() -> tuple[str, int, dict[str, str]]:
    # Stateless server: no standalone SSE stream and no sessions to delete.
    return "", 405, {"Allow": "POST"}
