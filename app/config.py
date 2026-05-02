"""Flask application configuration."""

import os


def parse_email_allowlist(value: str | None) -> frozenset[str]:
    """Parse a comma-separated allowlist into a normalized set."""
    if not value:
        return frozenset()

    return frozenset(email.strip() for email in value.split(",") if email.strip())


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB upload limit
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/recipes.db")
    IS_PRODUCTION = False
    GOOGLE_AUTH_ENABLED = os.environ.get("GOOGLE_AUTH_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_ALLOWED_EMAILS = parse_email_allowlist(
        os.environ.get("GOOGLE_ALLOWED_EMAILS", "")
    )
    HELICONE_ENABLED = os.environ.get("HELICONE_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    HELICONE_BASE_URL = os.environ.get("HELICONE_BASE_URL", "")
    HELICONE_API_KEY = os.environ.get("HELICONE_API_KEY", "")
    HELICONE_APP_NAME = os.environ.get("HELICONE_APP_NAME", "recipe-manager")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    IS_PRODUCTION = True
