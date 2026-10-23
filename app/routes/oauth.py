"""OAuth 2.1 authorization server for MCP clients, built on Authlib.

Authlib provides the authorization code grant, PKCE (RFC 7636), client
authentication, refresh tokens, revocation (RFC 7009), dynamic client
registration (RFC 7591) and the RFC 9207 iss parameter. This module adds what
the MCP authorization spec needs on top: discovery metadata (RFC 9728 and
RFC 8414), binding tokens to the /mcp resource (RFC 8707), the consent page
and the connected-apps page. The person approving access is whoever is
signed in to the web app, so the existing username/password login is reused.
"""

import hmac
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from authlib.integrations.flask_oauth2 import AuthorizationServer
from authlib.oauth2 import OAuth2Error
from authlib.oauth2.rfc6749 import InvalidRequestError, grants
from authlib.oauth2.rfc7009 import RevocationEndpoint
from authlib.oauth2.rfc7591 import ClientRegistrationEndpoint
from authlib.oauth2.rfc7591.errors import InvalidRedirectURIError
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oauth2.rfc9207 import IssuerParameter
from flask import (
    Blueprint,
    Flask,
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

from app.routes.auth import current_user
from app.storage.oauth import (
    LOOPBACK_HOSTS,
    MAX_CLIENTS,
    SCOPE,
    AuthorizationCode,
    Client,
    Token,
    consume_code,
    delete_grant,
    find_token,
    get_client,
    list_grants,
    prune_and_count_clients,
    save_client,
    save_code,
    save_token,
)

bp = Blueprint("oauth", __name__)

AUTH_METHODS = ["none", "client_secret_post", "client_secret_basic"]
ACCESS_TOKEN_TTL_SECONDS = 60 * 60
MAX_REDIRECT_URIS = 10


def mcp_enabled() -> bool:
    return bool(current_app.config.get("MCP_ENABLED", False))


def issuer() -> str:
    return request.url_root.rstrip("/")


def mcp_resource() -> str:
    return issuer() + "/mcp"


def protected_resource_metadata_url() -> str:
    return issuer() + "/.well-known/oauth-protected-resource/mcp"


def server_metadata() -> dict[str, Any]:
    base = issuer()
    return {
        "issuer": base,
        "authorization_endpoint": base + url_for("oauth.authorize"),
        "token_endpoint": base + url_for("oauth.token"),
        "registration_endpoint": base + url_for("oauth.register"),
        "revocation_endpoint": base + url_for("oauth.revoke"),
        "scopes_supported": [SCOPE],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": AUTH_METHODS,
        "revocation_endpoint_auth_methods_supported": AUTH_METHODS,
        "authorization_response_iss_parameter_supported": True,
    }


# --- Authlib wiring -------------------------------------------------------------


class S256CodeChallenge(CodeChallenge):
    """PKCE with S256 only, required for every client (OAuth 2.1)."""

    SUPPORTED_CODE_CHALLENGE_METHOD = ["S256"]
    DEFAULT_CODE_CHALLENGE_METHOD = "S256"

    def validate_code_challenge(self, grant: Any, redirect_uri: str) -> None:
        if not grant.request.payload.data.get("code_challenge"):
            raise InvalidRequestError("PKCE with code_challenge_method=S256 is required")
        super().validate_code_challenge(grant, redirect_uri)


class AuthorizationCodeGrant(grants.AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = AUTH_METHODS

    def save_authorization_code(self, code: str, request: Any) -> None:
        data = request.payload.data
        save_code(
            code,
            request.client.client_id,
            request.payload.redirect_uri or "",
            data["code_challenge"],
            data.get("code_challenge_method") or "S256",
            request.scope,
        )

    def query_authorization_code(self, code: str, client: Client) -> AuthorizationCode | None:
        # Deleted on lookup so that a failed exchange also burns the code.
        return consume_code(code, client.client_id)

    def delete_authorization_code(self, authorization_code: AuthorizationCode) -> None:
        pass

    def authenticate_user(self, authorization_code: AuthorizationCode) -> str:
        return "owner"  # single-user app: every grant belongs to the owner


class RefreshTokenGrant(grants.RefreshTokenGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = AUTH_METHODS
    INCLUDE_NEW_REFRESH_TOKEN = True

    def authenticate_refresh_token(self, refresh_token: str) -> Token | None:
        token = find_token(refresh_token, "refresh_hash")
        return token if token and token.is_refresh_token_valid() else None

    def authenticate_user(self, refresh_token: Token) -> str:
        return "owner"

    def revoke_old_credential(self, refresh_token: Token) -> None:
        delete_grant(refresh_token.id)


class TokenRevocationEndpoint(RevocationEndpoint):
    CLIENT_AUTH_METHODS = AUTH_METHODS

    def query_token(self, token_string: str, token_type_hint: str | None) -> Token | None:
        return find_token(token_string, "access_hash") or find_token(token_string, "refresh_hash")

    def revoke_token(self, token: Token, request: Any) -> None:
        delete_grant(token.id)


class ClientRegistration(ClientRegistrationEndpoint):
    def authenticate_token(self, request: Any) -> bool:
        return True  # open registration, as MCP clients expect

    def get_server_metadata(self) -> dict[str, Any]:
        return server_metadata()

    def extract_client_metadata(self, request: Any) -> dict[str, Any]:
        uris = (request.payload.data or {}).get("redirect_uris")
        if (
            not isinstance(uris, list)
            or not 0 < len(uris) <= MAX_REDIRECT_URIS
            or not all(_valid_redirect_uri(uri) for uri in uris)
        ):
            raise InvalidRedirectURIError(
                "redirect_uris must be https URLs or http loopback URLs"
            )
        metadata: dict[str, Any] = super().extract_client_metadata(request)
        if isinstance(metadata.get("client_name"), str):
            metadata["client_name"] = metadata["client_name"][:100]
        return metadata

    def generate_client_secret(self, request: Any) -> str | None:
        if (request.payload.data or {}).get("token_endpoint_auth_method") == "none":
            return None
        return secrets.token_urlsafe(32)

    def generate_client_info(self, request: Any) -> dict[str, Any]:
        info = super().generate_client_info(request)
        if info["client_secret"] is None:
            del info["client_secret"], info["client_secret_expires_at"]
        return dict(info)

    def save_client(
        self, client_info: dict[str, Any], client_metadata: dict[str, Any], request: Any
    ) -> Client:
        if prune_and_count_clients() >= MAX_CLIENTS:
            raise TemporarilyUnavailableError()
        return save_client(client_info, client_metadata)


class TemporarilyUnavailableError(OAuth2Error):
    error = "temporarily_unavailable"
    status_code = 503


class InvalidTargetError(OAuth2Error):
    """RFC 8707: the requested resource is not this server's /mcp."""

    error = "invalid_target"


class Issuer(IssuerParameter):
    def get_issuer(self) -> str:
        return issuer()


def _save_token(token: dict[str, Any], oauth_request: Any) -> None:
    save_token(token, oauth_request.client.client_id, mcp_resource())


def init_app(app: Flask) -> None:
    app.config.setdefault("OAUTH2_REFRESH_TOKEN_GENERATOR", True)
    app.config.setdefault(
        "OAUTH2_TOKEN_EXPIRES_IN",
        {"authorization_code": ACCESS_TOKEN_TTL_SECONDS, "refresh_token": ACCESS_TOKEN_TTL_SECONDS},
    )
    app.config.setdefault("OAUTH2_SCOPES_SUPPORTED", [SCOPE])

    server = AuthorizationServer(app, query_client=get_client, save_token=_save_token)
    server.register_grant(AuthorizationCodeGrant, [S256CodeChallenge(required=True)])
    server.register_grant(RefreshTokenGrant)
    server.register_endpoint(TokenRevocationEndpoint)
    server.register_endpoint(ClientRegistration)
    server.register_extension(Issuer())
    app.extensions["oauth_server"] = server


def _server() -> AuthorizationServer:
    return current_app.extensions["oauth_server"]


# --- Blueprint hooks ------------------------------------------------------------


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


# --- Discovery ------------------------------------------------------------------


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
    return jsonify(server_metadata())


# --- Dynamic client registration ------------------------------------------------


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


@bp.route("/register", methods=["POST"])
def register() -> Response:
    response: Response = _server().create_endpoint_response(ClientRegistration.ENDPOINT_NAME)
    response.headers["Cache-Control"] = "no-store"
    return response


# --- Authorization endpoint -----------------------------------------------------

AUTHORIZE_PARAMS = (
    "response_type",
    "client_id",
    "redirect_uri",
    "scope",
    "state",
    "code_challenge",
    "code_challenge_method",
    "resource",
)


def _bad_authorize_request(message: str) -> tuple[str, int]:
    # Never redirect to an unverified redirect_uri; show the error here instead.
    return render_template("oauth_error.html", message=message), 400


def _authorize_error(error: OAuth2Error) -> Response | tuple[str, int]:
    if not error.redirect_uri:
        return _bad_authorize_request(
            "This connection request is not valid. Try connecting again from your app."
        )
    response: Response = _server().handle_error_response(request, error)
    Issuer().add_issuer_parameter(_server(), response)
    return response


@bp.route("/authorize", methods=["GET", "POST"])
def authorize() -> Response | WerkzeugResponse | tuple[str, int]:
    # Reached only by a signed-in user: the login guard covers this endpoint.
    user = current_user() or {"username": "owner"}
    try:
        grant = _server().get_consent_grant(end_user=user)
        resource = request.values.get("resource")
        if resource and resource.rstrip("/") != mcp_resource():
            raise InvalidTargetError(
                "Unknown resource",
                redirect_uri=grant.redirect_uri,
                state=request.values.get("state"),
            )
    except OAuth2Error as error:
        return _authorize_error(error)

    if request.method == "GET":
        csrf_token = secrets.token_urlsafe(16)
        session["oauth_csrf"] = csrf_token
        params = {k: request.args[k] for k in AUTHORIZE_PARAMS if k in request.args}
        response = Response(
            render_template(
                "oauth_consent.html",
                client=grant.client,
                redirect_host=urlsplit(grant.redirect_uri).netloc,
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

    approved = request.form.get("decision") == "approve"
    return _server().create_authorization_response(
        grant_user=user if approved else None, grant=grant
    )


# --- Token and revocation endpoints ---------------------------------------------


@bp.route("/token", methods=["POST"])
def token() -> Response:
    resource = request.form.get("resource")
    if resource and resource.rstrip("/") != mcp_resource():
        return _server().handle_error_response(request, InvalidTargetError("Unknown resource"))
    return _server().create_token_response()


@bp.route("/revoke", methods=["POST"])
def revoke() -> Response:
    return _server().create_endpoint_response(TokenRevocationEndpoint.ENDPOINT_NAME)


# --- Connected apps (signed-in users only) --------------------------------------


@bp.route("/connected-apps")
def connected_apps() -> str:
    return render_template("connected_apps.html", grants=list_grants())


@bp.route("/connected-apps/<int:grant_id>/revoke", methods=["POST"])
def revoke_grant(grant_id: int) -> WerkzeugResponse:
    delete_grant(grant_id)
    return redirect(url_for("oauth.connected_apps"))
