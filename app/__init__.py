"""Flask application factory."""

import os

from dotenv import load_dotenv
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()


def validate_secret_key_config(app: Flask) -> None:
    if not app.config.get("IS_PRODUCTION") or app.config.get("TESTING"):
        return

    secret_key = app.config.get("SECRET_KEY", "")
    if not secret_key or secret_key == "dev-secret-key":
        raise RuntimeError(
            "Production requires SECRET_KEY to be set to a non-default value."
        )


def validate_auth_config(app: Flask) -> None:
    if not app.config.get("AUTH_ENABLED") or app.config.get("TESTING"):
        return

    missing = [
        key
        for key in ("AUTH_USERNAME", "AUTH_PASSWORD")
        if not app.config.get(key)
    ]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Auth is enabled, but these settings are missing: {joined}"
        )


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

    env = os.environ.get("FLASK_ENV", "development")
    if env == "production":
        app.config.from_object("app.config.ProductionConfig")
    else:
        app.config.from_object("app.config.DevelopmentConfig")

    if test_config:
        app.config.update(test_config)

    validate_secret_key_config(app)
    validate_auth_config(app)

    from app.storage.db import init_db
    init_db(app)

    from app.telemetry import configure_telemetry
    configure_telemetry(app)

    from app.routes.auth import bp as auth_bp
    from app.routes.recipes import bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(bp)

    return app
