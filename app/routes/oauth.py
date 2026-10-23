"""OAuth 2.1 authorization server for MCP clients.

Implements what the MCP authorization spec asks of a combined resource and
authorization server: protected resource metadata (RFC 9728), authorization
server metadata (RFC 8414), dynamic client registration (RFC 7591), the
authorization code grant with mandatory PKCE (S256), refresh token rotation
and token revocation (RFC 7009). The person approving access is whoever is
signed in to the web app, so the existing username/password login is reused.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlsplit

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers import Response as WerkzeugResponse

from app.storage.oauth import (
    Client,
    consume_code,
    create_code,
    delete_grant,
    get_client,
    issue_tokens,
    list_grants,
    register_client,
    revoke_token,
    rotate_refresh_token,
)

bp = Blueprint("oauth", __name__)

SCOPE = "recipes:read"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
AUTH_METHODS = ("none", "client_secret_post", "client_secret_basic")
MAX_REDIRECT_URIS = 10

# Endpoints called by MCP clients rather than by a signed-in browser.
PUBLIC_ENDPOINTS = {
    "oauth.protected_resource_metadata",
    "oauth.authorization_server_metadata",
    "oauth.register",
    "oauth.token",
    "oauth.revoke",
}


def mcp_enabled() -> bool:
    return bool(current_app.config.get("MCP_ENABLED", False))


def issuer() -> str:
    return request.url_root.rstrip("/")


def mcp_resource() -> str:
    return issuer() + "/mcp"


def protected_resource_metadata_url() -> str:
    return issuer() + "/.well-known/oauth-protected-resource/mcp"


@bp.before_request
def require_mcp_enabled() -> None:
    if not mcp_enabled():
        abort(404)


@bp.app_context_processor
def inject_mcp_enabled() -> dict[str, bool]:
    return {"mcp_enabled": mcp_enabled()}


@bp.app_template_filter("timestamp")
def format_timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    return response


# --- Discovery ---------------------------------------------------------------


@bp.route("/.well-known/oauth-protected-resource")
@bp.route("/.well-known/oauth-protected-resource/mcp")
def protected_resource_metadata() -> Response:
    return jsonify(
        resource=mcp_resource(),
        authorization_servers=[issuer()],
        scopes_supported=[SCOPE],
        bearer_methods_supported=["header"],
        resource_name="Recipe Manager",
    )


@bp.route("/.well-known/oauth-authorization-server")
def authorization_server_metadata() -> Response:
    base = issuer()
    return jsonify(
        issuer=base,
        authorization_endpoint=base + url_for("oauth.authorize"),
        token_endpoint=base + url_for("oauth.token"),
        registration_endpoint=base + url_for("oauth.register"),
        revocation_endpoint=base + url_for("oauth.revoke"),
        scopes_supported=[SCOPE],
        response_types_supported=["code"],
        grant_types_supported=["authorization_code", "refresh_token"],
        code_challenge_methods_supported=["S256"],
        token_endpoint_auth_methods_supported=list(AUTH_METHODS),
        revocation_endpoint_auth_methods_supported=list(AUTH_METHODS),
        authorization_response_iss_parameter_supported=True,
    )


# --- Dynamic client registration ----------------------------------------------


def _valid_redirect_uri(uri: Any) -> bool:
    if not isinstance(uri, str) or len(uri) > 2000:
        return False
    parts = urlsplit(uri)
    if parts.fragment or not parts.hostname:
        return False
    if parts.scheme == "https":
        return True
    # Native apps listen on a loopback port (RFC 8252 section 7.3).
    return parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS


def _registration_error(description: str, error: str = "invalid_client_metadata") -> tuple[Response, int]:
    return jsonify(error=error, error_description=description), 400


@bp.route("/register", methods=["POST"])
def register() -> tuple[Response, int]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _registration_error("Expected a JSON object")

    redirect_uris = body.get("redirect_uris")
    if (
        not isinstance(redirect_uris, list)
        or not 0 < len(redirect_uris) <= MAX_REDIRECT_URIS
        or not all(_valid_redirect_uri(uri) for uri in redirect_uris)
    ):
        return _registration_error(
            "redirect_uris must be https URLs or http loopback URLs",
            "invalid_redirect_uri",
        )

    auth_method = body.get("token_endpoint_auth_method", "client_secret_basic")
    if auth_method not in AUTH_METHODS:
        return _registration_error("Unsupported token_endpoint_auth_method")
    if not set(body.get("grant_types", ["authorization_code"])) <= {
        "authorization_code",
        "refresh_token",
    }:
        return _registration_error("Unsupported grant_types")
    if body.get("response_types", ["code"]) != ["code"]:
        return _registration_error("Unsupported response_types")

    client_name = body.get("client_name")
    client_name = client_name[:100] if isinstance(client_name, str) else None

    registered = register_client(client_name, redirect_uris, auth_method)
    if registered is None:
        return jsonify(error="temporarily_unavailable"), 503
    client, secret = registered

    response: dict[str, Any] = {
        "client_id": client.client_id,
        "client_name": client.client_name,
        "redirect_uris": client.redirect_uris,
        "token_endpoint_auth_method": client.auth_method,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "scope": SCOPE,
    }
    if secret:
        response["client_secret"] = secret
        response["client_secret_expires_at"] = 0
    return _no_store(jsonify(response)), 201


# --- Authorization endpoint ----------------------------------------------------


def _redirect_uri_allowed(client: Client, uri: str) -> bool:
    if uri in client.redirect_uris:
        return True
    # Loopback redirects may use any port (RFC 8252 section 7.3).
    parts = urlsplit(uri)
    if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS:
        return False
    for registered in client.redirect_uris:
        r = urlsplit(registered)
        if (r.scheme, r.hostname, r.path, r.query) == (
            parts.scheme,
            parts.hostname,
            parts.path,
            parts.query,
        ):
            return True
    return False


def _redirect_with(redirect_uri: str, **params: str | None) -> WerkzeugResponse:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    separator = "&" if urlsplit(redirect_uri).query else "?"
    return redirect(f"{redirect_uri}{separator}{query}")


class AuthorizeRejected(Exception):
    def __init__(self, response: WerkzeugResponse | tuple[str, int]) -> None:
        super().__init__()
        self.response = response


def _bad_authorize_request(message: str) -> tuple[str, int]:
    # Never redirect to an unverified redirect_uri; show the error here instead.
    return render_template("oauth_error.html", message=message), 400


def _validate_authorize(params: Any) -> tuple[Client, dict[str, str]]:
    client = get_client(params.get("client_id", ""))
    if client is None:
        raise AuthorizeRejected(
            _bad_authorize_request("Unknown client. Try connecting again from your app.")
        )
    redirect_uri = params.get("redirect_uri", "")
    if not _redirect_uri_allowed(client, redirect_uri):
        raise AuthorizeRejected(
            _bad_authorize_request("The redirect address does not match this client.")
        )

    state = params.get("state")

    def fail(error: str, description: str) -> AuthorizeRejected:
        return AuthorizeRejected(
            _redirect_with(
                redirect_uri, error=error, error_description=description, state=state, iss=issuer()
            )
        )

    if params.get("response_type") != "code":
        raise fail("unsupported_response_type", "Only response_type=code is supported")
    challenge = params.get("code_challenge", "")
    if params.get("code_challenge_method") != "S256" or not 43 <= len(challenge) <= 128:
        raise fail("invalid_request", "PKCE with code_challenge_method=S256 is required")
    requested_scope = params.get("scope") or SCOPE
    if set(requested_scope.split()) - {SCOPE}:
        raise fail("invalid_scope", f"Only the {SCOPE} scope is supported")
    resource = params.get("resource")
    if resource and resource.rstrip("/") != mcp_resource():
        raise fail("invalid_target", "Unknown resource")

    return client, {
        "client_id": client.client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": SCOPE,
        "state": state or "",
    }


@bp.route("/authorize", methods=["GET", "POST"])
def authorize() -> Response | WerkzeugResponse | tuple[str, int]:
    # Reached only by a signed-in user: the login guard covers this endpoint.
    source = request.args if request.method == "GET" else request.form
    try:
        client, params = _validate_authorize(source)
    except AuthorizeRejected as rejected:
        return rejected.response

    if request.method == "GET":
        csrf_token = secrets.token_urlsafe(16)
        session["oauth_csrf"] = csrf_token
        response = Response(
            render_template(
                "oauth_consent.html",
                client=client,
                redirect_host=urlsplit(params["redirect_uri"]).netloc,
                params=params,
                csrf_token=csrf_token,
            )
        )
        response.headers["X-Frame-Options"] = "DENY"
        return response

    expected_csrf = session.pop("oauth_csrf", None)
    if not expected_csrf or not hmac.compare_digest(
        request.form.get("csrf_token", ""), expected_csrf
    ):
        return _bad_authorize_request("This approval form expired. Try connecting again.")

    state = params["state"] or None
    if request.form.get("decision") != "approve":
        return _redirect_with(
            params["redirect_uri"], error="access_denied", state=state, iss=issuer()
        )

    code = create_code(
        client.client_id,
        params["redirect_uri"],
        params["code_challenge"],
        params["scope"],
        mcp_resource(),
    )
    return _redirect_with(params["redirect_uri"], code=code, state=state, iss=issuer())


# --- Token and revocation endpoints -------------------------------------------


def _token_error(error: str, description: str | None = None, status: int = 400) -> tuple[Response, int]:
    body = {"error": error}
    if description:
        body["error_description"] = description
    return _no_store(jsonify(body)), status


def _authenticate_client() -> Client | None:
    auth = request.authorization
    if auth is not None and auth.type == "basic":
        client_id, secret = auth.username or "", auth.password
    else:
        client_id = request.form.get("client_id", "")
        secret = request.form.get("client_secret")

    client = get_client(client_id)
    if client is None:
        return None
    if client.auth_method == "none":
        return client if secret is None else None
    return client if client.check_secret(secret) else None


def _pkce_matches(verifier: str, challenge: str) -> bool:
    if not 43 <= len(verifier) <= 128:
        return False
    digest = hashlib.sha256(verifier.encode("ascii", errors="replace")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return hmac.compare_digest(computed, challenge)


@bp.route("/token", methods=["POST"])
def token() -> Response | tuple[Response, int]:
    client = _authenticate_client()
    if client is None:
        return _token_error("invalid_client", status=401)

    grant_type = request.form.get("grant_type")
    if grant_type == "authorization_code":
        code = consume_code(request.form.get("code", ""))
        if (
            code is None
            or code.client_id != client.client_id
            or code.redirect_uri != request.form.get("redirect_uri")
            or not _pkce_matches(request.form.get("code_verifier", ""), code.code_challenge)
        ):
            return _token_error("invalid_grant")
        resource = request.form.get("resource")
        if resource and resource.rstrip("/") != code.resource:
            return _token_error("invalid_target")
        issued = issue_tokens(client.client_id, code.scope, code.resource)
    elif grant_type == "refresh_token":
        rotated = rotate_refresh_token(client.client_id, request.form.get("refresh_token", ""))
        if rotated is None:
            return _token_error("invalid_grant")
        issued = rotated
    else:
        return _token_error("unsupported_grant_type")

    return _no_store(
        jsonify(
            access_token=issued.access_token,
            token_type="Bearer",
            expires_in=issued.expires_in,
            refresh_token=issued.refresh_token,
            scope=issued.scope,
        )
    )


@bp.route("/revoke", methods=["POST"])
def revoke() -> Response | tuple[Response, int] | tuple[str, int]:
    client = _authenticate_client()
    if client is None:
        return _token_error("invalid_client", status=401)
    revoke_token(client.client_id, request.form.get("token", ""))
    return "", 200


# --- Connected apps (signed-in users only) ------------------------------------


@bp.route("/connected-apps")
def connected_apps() -> str:
    return render_template("connected_apps.html", grants=list_grants())


@bp.route("/connected-apps/<int:grant_id>/revoke", methods=["POST"])
def revoke_grant(grant_id: int) -> WerkzeugResponse:
    delete_grant(grant_id)
    return redirect(url_for("oauth.connected_apps"))
