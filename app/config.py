"""Flask application configuration."""

import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB upload limit
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/recipes.db")
    IS_PRODUCTION = False
    AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "")
    AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")
    HONEYCOMB_API_KEY = os.environ.get("HONEYCOMB_API_KEY", "")
    OTEL_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "recipe-manager")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    IS_PRODUCTION = True
