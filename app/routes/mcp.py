"""MCP Streamable HTTP endpoint, protected by OAuth access tokens."""

import json
from urllib.parse import urlsplit

from flask import Blueprint, Response, abort, jsonify, request

from app.mcp.protocol import (
    INVALID_REQUEST,
    PARSE_ERROR,
    SUPPORTED_PROTOCOL_VERSIONS,
    error_response,
    handle_message,
)
from app.routes.oauth import (
    SCOPE,
    mcp_enabled,
    mcp_resource,
    protected_resource_metadata_url,
)
from app.storage.oauth import validate_access_token

bp = Blueprint("mcp", __name__)


def _unauthorized(token_sent: bool) -> Response:
    # Points clients at the metadata that starts OAuth discovery.
    challenge = f'Bearer resource_metadata="{protected_resource_metadata_url()}", scope="{SCOPE}"'
    if token_sent:
        challenge += ', error="invalid_token"'
    response = jsonify(error="invalid_token" if token_sent else "unauthorized")
    response.status_code = 401
    response.headers["WWW-Authenticate"] = challenge
    return response


@bp.before_request
def require_token() -> Response | None:
    if not mcp_enabled():
        abort(404)

    # Reject cross-site browser requests (DNS rebinding protection).
    origin = request.headers.get("Origin")
    if origin and urlsplit(origin).netloc != request.host:
        abort(403)

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return _unauthorized(token_sent=False)
    if not validate_access_token(token, mcp_resource()):
        return _unauthorized(token_sent=True)
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
