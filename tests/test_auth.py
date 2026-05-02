"""Tests for Google auth routes and request guard."""

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from app import create_app
from app.config import parse_email_allowlist


@pytest.fixture
def auth_app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "auth-test-secret",
            "GOOGLE_AUTH_ENABLED": True,
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
            "GOOGLE_ALLOWED_EMAILS": frozenset({"chef@example.com"}),
            "DATABASE_PATH": str(tmp_path / "auth-test.db"),
        }
    )


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


class TestAuthGuard:
    def test_protected_route_redirects_to_login(self, auth_client):
        response = auth_client.get("/")

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login?next=/")

    def test_login_page_renders(self, auth_client):
        response = auth_client.get("/login")

        assert response.status_code == 200
        assert b"Sign in with Google" in response.data
        assert b'<a href="/login">Sign In</a>' not in response.data

    def test_htmx_request_gets_hx_redirect(self, auth_client):
        response = auth_client.post(
            "/recipes/save",
            headers={"HX-Request": "true"},
            data={},
        )

        assert response.status_code == 401
        assert response.headers["HX-Redirect"] == "/login"


class TestGoogleFlow:
    def test_google_login_redirects_to_google(self, auth_client):
        response = auth_client.get("/auth/google?next=/recipes/add")

        assert response.status_code == 302
        parsed = urlparse(response.headers["Location"])
        params = parse_qs(parsed.query)

        assert parsed.netloc == "accounts.google.com"
        assert params["client_id"] == ["client-id"]
        assert params["redirect_uri"] == ["http://localhost/auth/google/callback"]
        assert params["state"]
        assert params["nonce"]

        with auth_client.session_transaction() as session_data:
            assert session_data["post_login_redirect"] == "/recipes/add"
            assert session_data["google_oauth_state"] == params["state"][0]
            assert session_data["google_oauth_nonce"] == params["nonce"][0]

    @patch("app.routes.auth.id_token.verify_oauth2_token")
    @patch("app.routes.auth.requests.post")
    def test_callback_authenticates_allowed_email(
        self,
        mock_post,
        mock_verify_token,
        auth_client,
    ):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id_token": "signed-token"}
        mock_post.return_value = mock_response
        mock_verify_token.return_value = {
            "nonce": "expected-nonce",
            "email": "chef@example.com",
            "email_verified": True,
            "name": "Chef User",
        }

        with auth_client.session_transaction() as session_data:
            session_data["google_oauth_state"] = "expected-state"
            session_data["google_oauth_nonce"] = "expected-nonce"
            session_data["post_login_redirect"] = "/recipes/add"

        response = auth_client.get("/auth/google/callback?state=expected-state&code=abc")

        assert response.status_code == 302
        assert response.headers["Location"] == "/recipes/add"

        with auth_client.session_transaction() as session_data:
            assert session_data["user"]["email"] == "chef@example.com"
            assert session_data["user"]["name"] == "Chef User"

    @patch("app.routes.auth.id_token.verify_oauth2_token")
    @patch("app.routes.auth.requests.post")
    def test_callback_rejects_email_not_on_allowlist(
        self,
        mock_post,
        mock_verify_token,
        auth_client,
    ):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id_token": "signed-token"}
        mock_post.return_value = mock_response
        mock_verify_token.return_value = {
            "nonce": "expected-nonce",
            "email": "intruder@example.com",
            "email_verified": True,
        }

        with auth_client.session_transaction() as session_data:
            session_data["google_oauth_state"] = "expected-state"
            session_data["google_oauth_nonce"] = "expected-nonce"

        response = auth_client.get("/auth/google/callback?state=expected-state&code=abc")

        assert response.status_code == 403
        assert b"not on the allowed Google account list" in response.data

        with auth_client.session_transaction() as session_data:
            assert "user" not in session_data

    def test_logout_clears_session(self, auth_client):
        with auth_client.session_transaction() as session_data:
            session_data["user"] = {"email": "chef@example.com"}

        response = auth_client.post("/logout")

        assert response.status_code == 302
        assert response.headers["Location"] == "/login"

        with auth_client.session_transaction() as session_data:
            assert "user" not in session_data


class TestStartupValidation:
    def test_google_allowlist_parser_handles_commas_and_whitespace(self):
        assert parse_email_allowlist(
            " chef@example.com, sous@example.com ,, baker@example.com "
        ) == frozenset(
            {"chef@example.com", "sous@example.com", "baker@example.com"}
        )

    def test_google_auth_requires_allowed_emails(self, tmp_path):
        with pytest.raises(RuntimeError, match="GOOGLE_ALLOWED_EMAILS"):
            create_app(
                {
                    "TESTING": False,
                    "SECRET_KEY": "auth-test-secret",
                    "GOOGLE_AUTH_ENABLED": True,
                    "GOOGLE_CLIENT_ID": "client-id",
                    "GOOGLE_CLIENT_SECRET": "client-secret",
                    "GOOGLE_ALLOWED_EMAILS": frozenset(),
                    "DATABASE_PATH": str(tmp_path / "auth-test.db"),
                }
            )

    def test_production_requires_non_default_secret_key(self, tmp_path):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app(
                {
                    "TESTING": False,
                    "IS_PRODUCTION": True,
                    "SECRET_KEY": "dev-secret-key",
                    "GOOGLE_AUTH_ENABLED": False,
                    "DATABASE_PATH": str(tmp_path / "auth-test.db"),
                }
            )

    def test_helicone_requires_base_url_when_enabled(self, tmp_path):
        with pytest.raises(RuntimeError, match="HELICONE_BASE_URL"):
            create_app(
                {
                    "TESTING": False,
                    "SECRET_KEY": "auth-test-secret",
                    "GOOGLE_AUTH_ENABLED": False,
                    "HELICONE_ENABLED": True,
                    "HELICONE_BASE_URL": "",
                    "DATABASE_PATH": str(tmp_path / "auth-test.db"),
                }
            )
