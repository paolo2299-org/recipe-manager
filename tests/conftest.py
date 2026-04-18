"""Shared test fixtures."""

import json

import pytest

from app import create_app


SAMPLE_RECIPE = {
    "title": "Test Cookies",
    "description": "Simple test cookies.",
    "servings": "12",
    "prep_time": "10 mins",
    "cook_time": "15 mins",
    "total_time": "25 mins",
    "ingredients": [
        {"quantity": "200", "unit": "g", "name": "flour", "notes": None},
        {"quantity": "100", "unit": "g", "name": "butter", "notes": "softened"},
    ],
    "steps": [
        {"step_number": 1, "instruction": "Mix dry ingredients."},
        {"step_number": 2, "instruction": "Add butter and combine."},
    ],
    "tags": ["baking", "easy"],
}

SAMPLE_RECIPE_DB = {
    **SAMPLE_RECIPE,
    "id": "abc123",
    "source_type": "url",
    "source_ref": "https://example.com/cookies",
    "created_at": None,
    "updated_at": None,
}


def _test_config(tmp_path, **overrides):
    config = {
        "TESTING": True,
        "GOOGLE_AUTH_ENABLED": False,
        "SECRET_KEY": "test-secret-key",
        "DATABASE_PATH": str(tmp_path / "test.db"),
    }
    config.update(overrides)
    return config


@pytest.fixture
def app(tmp_path):
    """Create a Flask app for testing with an isolated SQLite DB."""
    return create_app(_test_config(tmp_path))


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def sample_recipe():
    return SAMPLE_RECIPE.copy()


@pytest.fixture
def sample_recipe_json():
    return json.dumps(SAMPLE_RECIPE)


@pytest.fixture
def sample_recipe_db():
    return SAMPLE_RECIPE_DB.copy()
