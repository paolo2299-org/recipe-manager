"""Authentication routes and request guard."""

import hmac

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


bp = Blueprint("auth", __name__)

EXEMPT_ENDPOINTS = {"auth.login", "static", "recipes.health"}


def auth_enabled():
    return current_app.config.get("AUTH_ENABLED", False)


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
    return {"current_user": current_user(), "auth_enabled": auth_enabled()}


@bp.before_app_request
def require_login():
    if not auth_enabled():
        return None

    if request.endpoint in EXEMPT_ENDPOINTS or request.endpoint is None:
        return None

    if current_user():
        return None

    return build_login_redirect()


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not auth_enabled():
        return redirect(url_for("recipes.index"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        config_username = current_app.config.get("AUTH_USERNAME", "")
        config_password = current_app.config.get("AUTH_PASSWORD", "")

        username_ok = hmac.compare_digest(username, config_username)
        password_ok = hmac.compare_digest(password, config_password)

        if username_ok and password_ok:
            session["user"] = {"username": username}
            next_path = request.form.get("next", "")
            if not is_safe_next_url(next_path):
                next_path = url_for("recipes.index")
            return redirect(next_path)

        next_path = request.form.get("next", "")
        return render_template(
            "login.html",
            next_path=next_path,
            auth_error="Invalid username or password.",
        ), 401

    if current_user():
        return redirect(url_for("recipes.index"))

    next_path = request.args.get("next", "")
    return render_template("login.html", next_path=next_path)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
