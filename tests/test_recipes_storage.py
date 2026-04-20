"""Tests for app.storage.recipes — SQLite CRUD operations."""

import pytest

from app.schemas.recipe import Ingredient, Recipe, Step
from app.storage.calories import upsert_calorie
from app.storage.db import get_db
from app.storage.recipes import (
    delete_recipe,
    get_recipe,
    list_recipes,
    save_recipe,
    update_recipe,
)
from tests.conftest import SAMPLE_RECIPE


def _sample() -> Recipe:
    return Recipe.model_validate(SAMPLE_RECIPE)


@pytest.fixture
def ctx(app):
    """Push an app context so get_db() can open the per-test connection."""
    with app.app_context():
        yield


class TestSaveRecipe:
    def test_save_returns_id_and_roundtrips(self, ctx):
        recipe_id = save_recipe(_sample(), "url", "https://example.com")

        assert recipe_id.isdigit()
        stored = get_recipe(recipe_id)
        assert stored is not None
        assert stored.record_type == "recipe"
        assert stored.title == "Test Cookies"
        assert stored.source_type == "url"
        assert stored.source_ref == "https://example.com"
        assert [i.model_dump() for i in stored.ingredients] == SAMPLE_RECIPE["ingredients"]
        assert [s.model_dump() for s in stored.steps] == SAMPLE_RECIPE["steps"]
        assert stored.tags == SAMPLE_RECIPE["tags"]
        assert stored.id == recipe_id
        assert stored.created_at
        assert stored.updated_at

    def test_save_handles_missing_optional_fields(self, ctx):
        minimal = Recipe(
            title="Minimal",
            ingredients=[Ingredient(name="salt")],
            steps=[Step(step_number=1, instruction="Taste.")],
            tags=[],
        )

        recipe_id = save_recipe(minimal, "image", "note.jpg")
        stored = get_recipe(recipe_id)

        assert stored is not None
        assert stored.title == "Minimal"
        assert stored.description is None
        assert stored.servings is None

    def test_save_recipe_idea_allows_empty_ingredients_and_steps(self, ctx):
        idea = Recipe(
            record_type="idea",
            title="Chickpea curry",
            ingredients=[],
            steps=[],
            tags=["weeknight", "vegan"],
        )

        recipe_id = save_recipe(idea, "manual", "")
        stored = get_recipe(recipe_id)

        assert stored is not None
        assert stored.record_type == "idea"
        assert stored.ingredients == []
        assert stored.steps == []
        assert stored.tags == ["weeknight", "vegan"]


class TestGetRecipe:
    def test_not_found(self, ctx):
        assert get_recipe("999999") is None


class TestListRecipes:
    def test_returns_newest_first(self, ctx):
        first = save_recipe(_sample().model_copy(update={"title": "First"}), "url", "a")
        second = save_recipe(_sample().model_copy(update={"title": "Second"}), "url", "b")

        recipes = list_recipes()

        assert [r.title for r in recipes] == ["Second", "First"]
        assert recipes[0].id == second
        assert recipes[1].id == first

    def test_empty_database(self, ctx):
        assert list_recipes() == []

    def test_returns_all_recipes_by_default(self, ctx):
        for i in range(3):
            save_recipe(_sample().model_copy(update={"title": f"R{i}"}), "url", str(i))

        assert len(list_recipes()) == 3

    def test_respects_explicit_limit(self, ctx):
        for i in range(3):
            save_recipe(_sample().model_copy(update={"title": f"R{i}"}), "url", str(i))

        assert len(list_recipes(limit=2)) == 2


class TestUpdateRecipe:
    def test_update_roundtrips_changes(self, ctx):
        recipe_id = save_recipe(_sample(), "url", "https://example.com")

        db = get_db()
        db.execute(
            "UPDATE recipes SET updated_at = '2000-01-01 00:00:00' WHERE id = ?",
            (recipe_id,),
        )
        db.commit()

        updated = _sample().model_copy(
            update={
                "title": "Updated Cookies",
                "ingredients": [
                    Ingredient(quantity="400", unit="g", name="flour", notes=None),
                ],
                "steps": [
                    Step(step_number=99, instruction="Mix everything together."),
                ],
            }
        )

        update_recipe(recipe_id, updated)
        stored = get_recipe(recipe_id)

        assert stored is not None
        assert stored.title == "Updated Cookies"
        assert [i.model_dump() for i in stored.ingredients] == [
            {"quantity": "400", "unit": "g", "name": "flour", "notes": None},
        ]
        assert [s.model_dump() for s in stored.steps] == [
            {"step_number": 1, "instruction": "Mix everything together."}
        ]
        assert stored.updated_at != "2000-01-01 00:00:00"


class TestCaloriesPerServing:
    def test_populated_when_all_ingredients_resolve(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        upsert_calorie("butter", "g", 100, 720)

        recipe_id = save_recipe(_sample(), "url", "https://example.com")
        stored = get_recipe(recipe_id)

        assert stored is not None
        # (200/100*364 + 100/100*720) / 12 = (728 + 720) / 12 = 120.67
        assert stored.calories_per_serving == 120.7

    def test_null_when_any_ingredient_missing_calorie_row(self, ctx):
        upsert_calorie("flour", "g", 100, 364)

        recipe_id = save_recipe(_sample(), "url", "https://example.com")
        stored = get_recipe(recipe_id)

        assert stored is not None
        assert stored.calories_per_serving is None

    def test_recompute_on_update(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        upsert_calorie("butter", "g", 100, 720)

        recipe_id = save_recipe(_sample(), "url", "https://example.com")
        stored = get_recipe(recipe_id)
        assert stored is not None and stored.calories_per_serving is not None

        db = get_db()
        db.execute("DELETE FROM calories WHERE name_key = 'butter'")
        db.commit()

        update_recipe(recipe_id, _sample())
        updated_stored = get_recipe(recipe_id)
        assert updated_stored is not None
        assert updated_stored.calories_per_serving is None


class TestDeleteRecipe:
    def test_delete_removes_row(self, ctx):
        recipe_id = save_recipe(_sample(), "url", "x")

        delete_recipe(recipe_id)

        assert get_recipe(recipe_id) is None

    def test_delete_missing_is_noop(self, ctx):
        delete_recipe("999999")
