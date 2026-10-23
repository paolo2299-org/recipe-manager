"""Tests for the OAuth-protected /mcp endpoint and its authorization server."""

import base64
import hashlib
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from app import create_app, validate_mcp_config

BASE = "http://localhost"
REDIRECT_URI = "http://127.0.0.1:33418/callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test"}},
}


@pytest.fixture
def oauth_app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "oauth-test-secret",
            "AUTH_ENABLED": True,
            "AUTH_USERNAME": "chef",
            "AUTH_PASSWORD": "secret",
            "MCP_ENABLED": True,
            "DATABASE_PATH": str(tmp_path / "oauth-test.db"),
        }
    )


@pytest.fixture
def oauth_client(oauth_app):
    return oauth_app.test_client()


def register(client, **overrides):
    body = {
        "client_name": "Test Client",
        "redirect_uris": [REDIRECT_URI],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        **overrides,
    }
    return client.post("/register", json=body)


def authorize_params(client_id, **overrides):
    return {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "state": "xyz",
        "resource": f"{BASE}/mcp",
        **overrides,
    }


def log_in(client):
    client.post("/login", data={"username": "chef", "password": "secret"})


def approve(client, client_id, decision="approve", **overrides):
    """Sign in, open the consent page and submit it. Returns the redirect query."""
    log_in(client)
    page = client.get("/authorize", query_string=authorize_params(client_id, **overrides))
    assert page.status_code == 200, page.data
    form = dict(re.findall(r'name="([^"]+)" value="([^"]*)"', page.get_data(as_text=True)))
    form["decision"] = decision
    response = client.post("/authorize", data=form)
    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    return location, {k: v[0] for k, v in parse_qs(location.query).items()}


def exchange(client, client_id, code, **overrides):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": VERIFIER,
        "resource": f"{BASE}/mcp",
        **overrides,
    }
    return client.post("/token", data=data)


def connect(client):
    client_id = register(client).get_json()["client_id"]
    _, query = approve(client, client_id)
    tokens = exchange(client, client_id, query["code"]).get_json()
    return client_id, tokens


def call_mcp(client, access_token):
    return client.post("/mcp", json=INIT, headers={"Authorization": f"Bearer {access_token}"})


class TestDiscovery:
    def test_disabled_by_default(self, client):
        assert client.get("/.well-known/oauth-authorization-server").status_code == 404
        assert client.post("/mcp", json=INIT).status_code == 404

    def test_unauthenticated_mcp_points_to_metadata(self, oauth_client):
        response = oauth_client.post("/mcp", json=INIT)

        assert response.status_code == 401
        challenge = response.headers["WWW-Authenticate"]
        assert f'resource_metadata="{BASE}/.well-known/oauth-protected-resource/mcp"' in challenge

    def test_metadata_documents(self, oauth_client):
        resource = oauth_client.get("/.well-known/oauth-protected-resource/mcp").get_json()
        server = oauth_client.get("/.well-known/oauth-authorization-server").get_json()

        assert resource["resource"] == f"{BASE}/mcp"
        assert resource["authorization_servers"] == [BASE]
        assert server["issuer"] == BASE
        assert server["authorization_endpoint"] == f"{BASE}/authorize"
        assert server["registration_endpoint"] == f"{BASE}/register"
        assert server["code_challenge_methods_supported"] == ["S256"]


class TestRegistration:
    def test_public_client(self, oauth_client):
        response = register(oauth_client)

        assert response.status_code == 201
        body = response.get_json()
        assert body["client_id"]
        assert "client_secret" not in body

    def test_confidential_client_gets_secret(self, oauth_client):
        body = register(
            oauth_client,
            redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
            token_endpoint_auth_method="client_secret_post",
        ).get_json()

        assert body["client_secret"]

    @pytest.mark.parametrize(
        "uri",
        ["http://example.com/cb", "javascript:alert(1)", "https://example.com/cb#frag", "myapp://cb"],
    )
    def test_unsafe_redirect_uris_rejected(self, oauth_client, uri):
        response = register(oauth_client, redirect_uris=[uri])

        assert response.status_code == 400
        assert response.get_json()["error"] == "invalid_redirect_uri"


class TestAuthorize:
    def test_requires_login(self, oauth_client):
        client_id = register(oauth_client).get_json()["client_id"]
        response = oauth_client.get("/authorize", query_string=authorize_params(client_id))

        assert response.status_code == 302
        assert "/login?next=/authorize" in response.headers["Location"]

    def test_unknown_client_or_redirect_is_not_redirected(self, oauth_client):
        log_in(oauth_client)
        client_id = register(oauth_client).get_json()["client_id"]

        unknown = oauth_client.get("/authorize", query_string=authorize_params("nope"))
        wrong_uri = oauth_client.get(
            "/authorize",
            query_string=authorize_params(client_id, redirect_uri="https://evil.example/cb"),
        )

        assert unknown.status_code == 400
        assert wrong_uri.status_code == 400

    def test_pkce_is_required(self, oauth_client):
        log_in(oauth_client)
        client_id = register(oauth_client).get_json()["client_id"]
        response = oauth_client.get(
            "/authorize", query_string=authorize_params(client_id, code_challenge_method="plain")
        )

        query = parse_qs(urlsplit(response.headers["Location"]).query)
        assert query["error"] == ["invalid_request"]
        assert query["state"] == ["xyz"]

    def test_consent_page_names_client(self, oauth_client):
        log_in(oauth_client)
        client_id = register(oauth_client).get_json()["client_id"]
        response = oauth_client.get("/authorize", query_string=authorize_params(client_id))

        assert b"Test Client" in response.data
        assert b"127.0.0.1:33418" in response.data
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_deny(self, oauth_client):
        client_id = register(oauth_client).get_json()["client_id"]
        _, query = approve(oauth_client, client_id, decision="deny")

        assert query["error"] == "access_denied"
        assert query["state"] == "xyz"

    def test_post_without_csrf_token_is_rejected(self, oauth_client):
        log_in(oauth_client)
        client_id = register(oauth_client).get_json()["client_id"]
        response = oauth_client.post(
            "/authorize", data={**authorize_params(client_id), "decision": "approve"}
        )

        assert response.status_code == 400

    def test_loopback_redirect_may_change_port(self, oauth_client):
        client_id = register(oauth_client).get_json()["client_id"]
        location, query = approve(
            oauth_client, client_id, redirect_uri="http://127.0.0.1:50000/callback"
        )

        assert location.netloc == "127.0.0.1:50000"
        assert "code" in query


class TestTokens:
    def test_full_flow_grants_mcp_access(self, oauth_client):
        client_id = register(oauth_client).get_json()["client_id"]
        location, query = approve(oauth_client, client_id)

        assert query["state"] == "xyz"
        assert query["iss"] == BASE
        response = exchange(oauth_client, client_id, query["code"])
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        tokens = response.get_json()
        assert tokens["token_type"] == "Bearer"

        mcp = call_mcp(oauth_client, tokens["access_token"])
        assert mcp.status_code == 200
        assert mcp.get_json()["result"]["serverInfo"]["name"] == "recipe-manager"

    def test_code_is_single_use(self, oauth_client):
        client_id = register(oauth_client).get_json()["client_id"]
        _, query = approve(oauth_client, client_id)

        assert exchange(oauth_client, client_id, query["code"]).status_code == 200
        assert exchange(oauth_client, client_id, query["code"]).get_json()["error"] == "invalid_grant"

    def test_wrong_verifier_or_redirect_rejected(self, oauth_client):
        client_id = register(oauth_client).get_json()["client_id"]
        _, first = approve(oauth_client, client_id)
        _, second = approve(oauth_client, client_id)

        bad_verifier = exchange(oauth_client, client_id, first["code"], code_verifier="w" * 64)
        bad_redirect = exchange(
            oauth_client, client_id, second["code"], redirect_uri="http://127.0.0.1:1/other"
        )

        assert bad_verifier.get_json()["error"] == "invalid_grant"
        assert bad_redirect.get_json()["error"] == "invalid_grant"

    def test_other_client_cannot_redeem_code(self, oauth_client):
        client_id = register(oauth_client).get_json()["client_id"]
        other_id = register(oauth_client).get_json()["client_id"]
        _, query = approve(oauth_client, client_id)

        response = exchange(oauth_client, other_id, query["code"])

        assert response.get_json()["error"] == "invalid_grant"

    def test_confidential_client_must_authenticate(self, oauth_client):
        registered = register(oauth_client, token_endpoint_auth_method="client_secret_basic").get_json()
        client_id, secret = registered["client_id"], registered["client_secret"]
        _, first = approve(oauth_client, client_id)
        _, second = approve(oauth_client, client_id)

        no_secret = exchange(oauth_client, client_id, first["code"])
        basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
        with_secret = oauth_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": second["code"],
                "redirect_uri": REDIRECT_URI,
                "code_verifier": VERIFIER,
            },
            headers={"Authorization": f"Basic {basic}"},
        )

        assert no_secret.status_code == 401
        assert with_secret.status_code == 200

    def test_refresh_rotates_tokens(self, oauth_client):
        client_id, tokens = connect(oauth_client)

        refreshed = oauth_client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": client_id,
            },
        ).get_json()
        reused = oauth_client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": client_id,
            },
        )

        assert call_mcp(oauth_client, refreshed["access_token"]).status_code == 200
        assert call_mcp(oauth_client, tokens["access_token"]).status_code == 401
        assert reused.get_json()["error"] == "invalid_grant"

    def test_revocation(self, oauth_client):
        client_id, tokens = connect(oauth_client)

        response = oauth_client.post(
            "/revoke", data={"token": tokens["refresh_token"], "client_id": client_id}
        )

        assert response.status_code == 200
        assert call_mcp(oauth_client, tokens["access_token"]).status_code == 401

    def test_invalid_token_reported(self, oauth_client):
        response = call_mcp(oauth_client, "not-a-token")

        assert response.status_code == 401
        assert 'error="invalid_token"' in response.headers["WWW-Authenticate"]


class TestConnectedApps:
    def test_list_and_disconnect(self, oauth_client):
        _, tokens = connect(oauth_client)
        call_mcp(oauth_client, tokens["access_token"])

        page = oauth_client.get("/connected-apps")
        assert b"Test Client" in page.data
        grant_id = re.search(rb"/connected-apps/(\d+)/revoke", page.data).group(1).decode()

        oauth_client.post(f"/connected-apps/{grant_id}/revoke")

        assert call_mcp(oauth_client, tokens["access_token"]).status_code == 401
        assert b"No apps are connected" in oauth_client.get("/connected-apps").data

    def test_requires_login(self, oauth_client):
        assert oauth_client.get("/connected-apps").status_code == 302


def test_production_requires_login_for_mcp(app):
    app.config.update(TESTING=False, IS_PRODUCTION=True, MCP_ENABLED=True, AUTH_ENABLED=False)

    with pytest.raises(RuntimeError, match="MCP_ENABLED"):
        validate_mcp_config(app)
