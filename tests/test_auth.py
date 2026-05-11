"""Tests for auth routes and request guard."""

import pytest

from app import create_app


@pytest.fixture
def auth_app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "auth-test-secret",
            "AUTH_ENABLED": True,
            "AUTH_USERNAME": "chef",
            "AUTH_PASSWORD": "secret",
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
        assert b"Sign In" in response.data
        assert b'<a href="/login">Sign In</a>' not in response.data

    def test_htmx_request_gets_hx_redirect(self, auth_client):
        response = auth_client.post(
            "/recipes/save",
            headers={"HX-Request": "true"},
            data={},
        )

        assert response.status_code == 401
        assert response.headers["HX-Redirect"] == "/login"


class TestLoginFlow:
    def test_valid_credentials_log_in(self, auth_client):
        response = auth_client.post(
            "/login",
            data={"username": "chef", "password": "secret", "next": ""},
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/"

        with auth_client.session_transaction() as sess:
            assert sess["user"]["username"] == "chef"

    def test_valid_credentials_redirect_to_next(self, auth_client):
        response = auth_client.post(
            "/login",
            data={"username": "chef", "password": "secret", "next": "/recipes/add"},
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/recipes/add"

    def test_wrong_password_rejected(self, auth_client):
        response = auth_client.post(
            "/login",
            data={"username": "chef", "password": "wrong"},
        )

        assert response.status_code == 401
        assert b"Invalid username or password" in response.data

        with auth_client.session_transaction() as sess:
            assert "user" not in sess

    def test_wrong_username_rejected(self, auth_client):
        response = auth_client.post(
            "/login",
            data={"username": "intruder", "password": "secret"},
        )

        assert response.status_code == 401
        assert b"Invalid username or password" in response.data

    def test_logout_clears_session(self, auth_client):
        with auth_client.session_transaction() as sess:
            sess["user"] = {"username": "chef"}

        response = auth_client.post("/logout")

        assert response.status_code == 302
        assert response.headers["Location"] == "/login"

        with auth_client.session_transaction() as sess:
            assert "user" not in sess


class TestStartupValidation:
    def test_auth_requires_username_and_password(self, tmp_path):
        with pytest.raises(RuntimeError, match="AUTH_USERNAME"):
            create_app(
                {
                    "TESTING": False,
                    "SECRET_KEY": "auth-test-secret",
                    "AUTH_ENABLED": True,
                    "AUTH_USERNAME": "",
                    "AUTH_PASSWORD": "secret",
                    "DATABASE_PATH": str(tmp_path / "auth-test.db"),
                }
            )

    def test_auth_requires_password(self, tmp_path):
        with pytest.raises(RuntimeError, match="AUTH_PASSWORD"):
            create_app(
                {
                    "TESTING": False,
                    "SECRET_KEY": "auth-test-secret",
                    "AUTH_ENABLED": True,
                    "AUTH_USERNAME": "admin",
                    "AUTH_PASSWORD": "",
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
                    "AUTH_ENABLED": False,
                    "DATABASE_PATH": str(tmp_path / "auth-test.db"),
                }
            )
