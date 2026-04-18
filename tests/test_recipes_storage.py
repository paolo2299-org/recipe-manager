"""Tests for app.storage.recipes — SQLite CRUD operations."""

import pytest

from app.storage.recipes import (
    delete_recipe,
    get_recipe,
    list_recipes,
    save_recipe,
)
from tests.conftest import SAMPLE_RECIPE


@pytest.fixture
def ctx(app):
    """Push an app context so get_db() can open the per-test connection."""
    with app.app_context():
        yield


class TestSaveRecipe:
    def test_save_returns_id_and_roundtrips(self, ctx):
        recipe_id = save_recipe(SAMPLE_RECIPE, "url", "https://example.com")

        assert recipe_id.isdigit()
        stored = get_recipe(recipe_id)
        assert stored["title"] == "Test Cookies"
        assert stored["source_type"] == "url"
        assert stored["source_ref"] == "https://example.com"
        assert stored["ingredients"] == SAMPLE_RECIPE["ingredients"]
        assert stored["steps"] == SAMPLE_RECIPE["steps"]
        assert stored["tags"] == SAMPLE_RECIPE["tags"]
        assert stored["id"] == recipe_id
        assert stored["created_at"]
        assert stored["updated_at"]

    def test_save_handles_missing_optional_fields(self, ctx):
        minimal = {
            "title": "Minimal",
            "ingredients": [{"name": "salt"}],
            "steps": [{"step_number": 1, "instruction": "Taste."}],
            "tags": [],
        }

        recipe_id = save_recipe(minimal, "image", "note.jpg")
        stored = get_recipe(recipe_id)

        assert stored["title"] == "Minimal"
        assert stored["description"] is None
        assert stored["servings"] is None


class TestGetRecipe:
    def test_not_found(self, ctx):
        assert get_recipe("999999") is None


class TestListRecipes:
    def test_returns_newest_first(self, ctx):
        first = save_recipe({**SAMPLE_RECIPE, "title": "First"}, "url", "a")
        second = save_recipe({**SAMPLE_RECIPE, "title": "Second"}, "url", "b")

        recipes = list_recipes()

        assert [r["title"] for r in recipes] == ["Second", "First"]
        assert recipes[0]["id"] == second
        assert recipes[1]["id"] == first

    def test_empty_database(self, ctx):
        assert list_recipes() == []

    def test_respects_limit(self, ctx):
        for i in range(3):
            save_recipe({**SAMPLE_RECIPE, "title": f"R{i}"}, "url", str(i))

        assert len(list_recipes(limit=2)) == 2


class TestDeleteRecipe:
    def test_delete_removes_row(self, ctx):
        recipe_id = save_recipe(SAMPLE_RECIPE, "url", "x")

        delete_recipe(recipe_id)

        assert get_recipe(recipe_id) is None

    def test_delete_missing_is_noop(self, ctx):
        delete_recipe("999999")
