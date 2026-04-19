"""Tests for the calorie-editing routes."""

from unittest.mock import patch

import pytest

from app.schemas.recipe import Recipe
from app.storage.calories import get_calorie, upsert_calorie
from tests.conftest import SAMPLE_RECIPE_DB, make_recipe


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield


class TestDetailPageCalories:
    @patch("app.routes.recipes.get_recipe")
    def test_shows_add_calorie_link_when_null(self, mock_get, client):
        mock_get.return_value = make_recipe(calories_per_serving=None)

        response = client.get("/recipes/abc123")

        assert response.status_code == 200
        assert b"Add calorie information" in response.data
        assert b"/recipes/abc123/calories/edit" in response.data

    @patch("app.routes.recipes.get_recipe")
    def test_shows_value_when_set(self, mock_get, client):
        mock_get.return_value = make_recipe(calories_per_serving=217.0)

        response = client.get("/recipes/abc123")

        assert response.status_code == 200
        assert b"Calories per serving" in response.data
        assert b"217.0" in response.data

    @patch("app.routes.recipes.get_recipe")
    def test_hidden_for_ideas(self, mock_get, client):
        mock_get.return_value = Recipe(
            id="idea-1",
            record_type="idea",
            title="Chicken shawarma bowls",
            ingredients=[],
            steps=[],
            tags=["dinner"],
            source_type="manual",
            source_ref="",
        )

        response = client.get("/recipes/idea-1")

        assert response.status_code == 200
        assert b"Add calorie information" not in response.data
        assert b"Calories per serving" not in response.data


class TestEditCaloriesGet:
    def test_lists_missing_ingredients(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Minimal",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": "2", "name": "eggs"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "https://example.com",
            )

        response = client.get(f"/recipes/{recipe_id}/calories/edit")

        assert response.status_code == 200
        assert b"flour" in response.data
        assert b"eggs" in response.data
        assert b"Reference quantity" in response.data

    def test_redirects_when_nothing_missing(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            upsert_calorie("flour", "g", 100, 364)
            upsert_calorie("butter", "g", 100, 720)
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Roux",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "100", "unit": "g", "name": "flour"},
                            {"quantity": "100", "unit": "g", "name": "butter"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Cook."}],
                        "tags": [],
                    }
                ),
                "url",
                "https://example.com",
            )

        response = client.get(
            f"/recipes/{recipe_id}/calories/edit", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["Location"] == f"/recipes/{recipe_id}"

    @patch("app.routes.recipes.get_recipe")
    def test_404_for_missing_recipe(self, mock_get, client):
        mock_get.return_value = None
        response = client.get("/recipes/999/calories/edit")
        assert response.status_code == 404

    @patch("app.routes.recipes.get_recipe")
    def test_404_for_idea(self, mock_get, client):
        mock_get.return_value = Recipe(
            id="idea-1",
            record_type="idea",
            title="Idea",
            ingredients=[],
            steps=[],
            tags=[],
        )
        response = client.get("/recipes/idea-1/calories/edit")
        assert response.status_code == 404

    def test_redirects_to_quantities_when_unparseable_ingredient(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Dodgy amounts",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": "3 - 4", "unit": "tbsp", "name": "oil"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.get(
            f"/recipes/{recipe_id}/calories/edit", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["Location"] == (
            f"/recipes/{recipe_id}/ingredients/quantities"
        )

    def test_redirects_to_quantities_when_servings_unparseable(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            upsert_calorie("flour", "g", 100, 364)
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Ambiguous servings",
                        "servings": "4-6",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.get(
            f"/recipes/{recipe_id}/calories/edit", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["Location"] == (
            f"/recipes/{recipe_id}/ingredients/quantities"
        )

    def test_negligible_unparseable_does_not_redirect(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Salt to taste",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": None, "name": "salt"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.get(
            f"/recipes/{recipe_id}/calories/edit", follow_redirects=False
        )
        assert response.status_code == 200
        assert b"flour" in response.data


class TestEditIngredientQuantitiesGet:
    def test_lists_only_unparseable_ingredients(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Dodgy amounts",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": "3 - 4", "unit": "tbsp", "name": "oil"},
                            {"quantity": None, "name": "garlic"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.get(f"/recipes/{recipe_id}/ingredients/quantities")
        assert response.status_code == 200
        assert b"oil" in response.data
        assert b"garlic" in response.data
        # flour has a parseable quantity and is not listed as a row to fix
        assert response.data.count(b"<legend>") == 2

    def test_shows_servings_field_when_servings_unparseable(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Ambiguous servings",
                        "servings": "4-6",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.get(f"/recipes/{recipe_id}/ingredients/quantities")
        assert response.status_code == 200
        assert b'name="servings"' in response.data
        # no ingredient fieldsets, only the servings one
        assert response.data.count(b"<legend>") == 1

    def test_redirects_when_nothing_to_fix(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Clean recipe",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": "2", "name": "eggs"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.get(
            f"/recipes/{recipe_id}/ingredients/quantities", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["Location"] == f"/recipes/{recipe_id}/calories/edit"

    @patch("app.routes.recipes.get_recipe")
    def test_404_for_missing_recipe(self, mock_get, client):
        mock_get.return_value = None
        response = client.get("/recipes/999/ingredients/quantities")
        assert response.status_code == 404

    @patch("app.routes.recipes.get_recipe")
    def test_404_for_idea(self, mock_get, client):
        mock_get.return_value = Recipe(
            id="idea-1",
            record_type="idea",
            title="Idea",
            ingredients=[],
            steps=[],
            tags=[],
        )
        response = client.get("/recipes/idea-1/ingredients/quantities")
        assert response.status_code == 404


class TestSaveIngredientQuantities:
    def test_valid_submission_updates_and_redirects(self, ctx, client, app):
        from app.storage.recipes import get_recipe, save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Dodgy amounts",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": "3 - 4", "unit": "tbsp", "name": "oil"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.post(
            f"/recipes/{recipe_id}/ingredients/quantities",
            data={"index": ["1"], "quantity": ["3"], "unit": ["tbsp"]},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == f"/recipes/{recipe_id}/calories/edit"

        with app.app_context():
            stored = get_recipe(recipe_id)
            assert stored is not None
            assert stored.ingredients[0].name == "flour"
            assert stored.ingredients[1].quantity == "3"
            assert stored.ingredients[1].unit == "tbsp"

    def test_blank_unit_saved_as_none(self, ctx, client, app):
        from app.storage.recipes import get_recipe, save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "No unit",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": None, "unit": "cloves", "name": "garlic"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.post(
            f"/recipes/{recipe_id}/ingredients/quantities",
            data={"index": ["1"], "quantity": ["2"], "unit": [""]},
            follow_redirects=False,
        )

        assert response.status_code == 302
        with app.app_context():
            stored = get_recipe(recipe_id)
            assert stored is not None
            assert stored.ingredients[1].quantity == "2"
            assert stored.ingredients[1].unit is None

    def test_updates_servings(self, ctx, client, app):
        from app.storage.recipes import get_recipe, save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Ambiguous servings",
                        "servings": "4-6",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.post(
            f"/recipes/{recipe_id}/ingredients/quantities",
            data={"servings": "5"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == f"/recipes/{recipe_id}/calories/edit"
        with app.app_context():
            stored = get_recipe(recipe_id)
            assert stored is not None
            assert stored.servings == "5"

    def test_unparseable_servings_shows_error(self, ctx, client, app):
        from app.storage.recipes import get_recipe, save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Ambiguous servings",
                        "servings": "4-6",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.post(
            f"/recipes/{recipe_id}/ingredients/quantities",
            data={"servings": "a lot"},
        )

        assert response.status_code == 200
        assert b"Could not save amounts" in response.data
        with app.app_context():
            stored = get_recipe(recipe_id)
            assert stored is not None
            assert stored.servings == "4-6"

    def test_updates_servings_and_ingredient_together(self, ctx, client, app):
        from app.storage.recipes import get_recipe, save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Both broken",
                        "servings": "4-6",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": "3 - 4", "unit": "tbsp", "name": "oil"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.post(
            f"/recipes/{recipe_id}/ingredients/quantities",
            data={
                "servings": "5",
                "index": ["1"],
                "quantity": ["3"],
                "unit": ["tbsp"],
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        with app.app_context():
            stored = get_recipe(recipe_id)
            assert stored is not None
            assert stored.servings == "5"
            assert stored.ingredients[1].quantity == "3"

    def test_still_unparseable_quantity_shows_error(self, ctx, client, app):
        from app.storage.recipes import get_recipe, save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Still bad",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": "3 - 4", "unit": "tbsp", "name": "oil"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.post(
            f"/recipes/{recipe_id}/ingredients/quantities",
            data={"index": ["1"], "quantity": ["two"], "unit": ["tbsp"]},
        )

        assert response.status_code == 200
        assert b"Could not save amounts" in response.data
        with app.app_context():
            stored = get_recipe(recipe_id)
            assert stored is not None
            assert stored.ingredients[1].quantity == "3 - 4"


class TestSaveCalories:
    def test_upserts_and_recomputes(self, ctx, client, app):
        from app.storage.recipes import get_recipe, save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Shortbread",
                        "servings": "12",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": "100", "unit": "g", "name": "butter"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )
            stored = get_recipe(recipe_id)
            assert stored is not None and stored.calories_per_serving is None

        response = client.post(
            f"/recipes/{recipe_id}/calories/edit",
            data={
                "name": ["flour", "butter"],
                "unit": ["g", "g"],
                "reference_quantity": ["100", "100"],
                "calories": ["364", "720"],
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == f"/recipes/{recipe_id}"

        with app.app_context():
            flour = get_calorie("flour", "g")
            butter = get_calorie("butter", "g")
            assert flour is not None and flour.calories == 364
            assert butter is not None and butter.calories == 720
            stored = get_recipe(recipe_id)
            assert stored is not None
            # (200/100*364 + 100/100*720) / 12 = 120.67
            assert stored.calories_per_serving == 120.7

    def test_blank_rows_are_skipped(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Partial",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": "2", "name": "eggs"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.post(
            f"/recipes/{recipe_id}/calories/edit",
            data={
                "name": ["flour", "eggs"],
                "unit": ["g", ""],
                "reference_quantity": ["100", ""],
                "calories": ["364", ""],
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        with app.app_context():
            flour = get_calorie("flour", "g")
            assert flour is not None and flour.calories == 364
            assert get_calorie("eggs", None) is None

    def test_partial_row_shows_error(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Partial",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.post(
            f"/recipes/{recipe_id}/calories/edit",
            data={
                "name": ["flour"],
                "unit": ["g"],
                "reference_quantity": ["100"],
                "calories": [""],
            },
        )

        assert response.status_code == 200
        assert b"Could not save calorie information" in response.data
