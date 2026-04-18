"""Google authentication routes and request guard."""

import secrets
from urllib.parse import urlencode

import requests
from flask import (
    Blueprint,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


bp = Blueprint("auth", __name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
EXEMPT_ENDPOINTS = {"auth.login", "auth.google_login", "auth.google_callback", "static"}


def google_auth_enabled():
    return current_app.config.get("GOOGLE_AUTH_ENABLED", False)


def is_safe_next_url(value):
    return bool(value) and value.startswith("/") and not value.startswith("//")


def current_user():
    return session.get("user")


def build_login_redirect():
    next_path = request.full_path if request.method == "GET" else None
    if next_path and next_path.endswith("?"):
        next_path = next_path[:-1]

    login_url = url_for("auth.login")
    if is_safe_next_url(next_path) and next_path != url_for("auth.login"):
        login_url = url_for("auth.login", next=next_path)

    if request.headers.get("HX-Request") == "true":
        response = make_response("", 401)
        response.headers["HX-Redirect"] = login_url
        return response

    return redirect(login_url)


@bp.app_context_processor
def inject_current_user():
    return {"current_user": current_user(), "google_auth_enabled": google_auth_enabled()}


@bp.before_app_request
def require_login():
    if not google_auth_enabled():
        return None

    if request.endpoint in EXEMPT_ENDPOINTS or request.endpoint is None:
        return None

    if current_user():
        return None

    return build_login_redirect()


@bp.route("/login")
def login():
    if not google_auth_enabled():
        return redirect(url_for("recipes.index"))

    if current_user():
        return redirect(url_for("recipes.index"))

    next_path = request.args.get("next", "")
    return render_template("login.html", next_path=next_path)


@bp.route("/auth/google")
def google_login():
    if not google_auth_enabled():
        return redirect(url_for("recipes.index"))

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    next_path = request.args.get("next", "")

    session["google_oauth_state"] = state
    session["google_oauth_nonce"] = nonce
    if is_safe_next_url(next_path):
        session["post_login_redirect"] = next_path
    else:
        session.pop("post_login_redirect", None)

    params = {
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "redirect_uri": url_for("auth.google_callback", _external=True),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@bp.route("/auth/google/callback")
def google_callback():
    if not google_auth_enabled():
        return redirect(url_for("recipes.index"))

    expected_state = session.pop("google_oauth_state", None)
    expected_nonce = session.pop("google_oauth_nonce", None)
    actual_state = request.args.get("state")
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return render_template(
            "login.html",
            next_path=session.pop("post_login_redirect", ""),
            auth_error=f"Google sign-in failed: {error}",
        ), 400

    if not code or not expected_state or actual_state != expected_state:
        return render_template(
            "login.html",
            next_path=session.pop("post_login_redirect", ""),
            auth_error="Google sign-in could not be verified. Please try again.",
        ), 400

    token_response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": current_app.config["GOOGLE_CLIENT_ID"],
            "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": url_for("auth.google_callback", _external=True),
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    token_response.raise_for_status()
    token_payload = token_response.json()

    token_info = id_token.verify_oauth2_token(
        token_payload["id_token"],
        google_requests.Request(),
        current_app.config["GOOGLE_CLIENT_ID"],
    )
    if token_info.get("nonce") != expected_nonce:
        return render_template(
            "login.html",
            next_path=session.pop("post_login_redirect", ""),
            auth_error="Google sign-in could not be verified. Please try again.",
        ), 400

    email = token_info.get("email", "").lower()
    allowed_emails = current_app.config.get("GOOGLE_ALLOWED_EMAILS", frozenset())

    if not token_info.get("email_verified") or email not in allowed_emails:
        session.clear()
        return render_template("unauthorized.html", email=email), 403

    session["user"] = {
        "email": email,
        "name": token_info.get("name") or email,
        "picture": token_info.get("picture"),
    }

    next_path = session.pop("post_login_redirect", url_for("recipes.index"))
    if not is_safe_next_url(next_path):
        next_path = url_for("recipes.index")
    return redirect(next_path)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
