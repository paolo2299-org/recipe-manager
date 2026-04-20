"""Tests for the calorie breakdown view and single-ingredient edit flow."""

from unittest.mock import patch

import pytest

from app.schemas.recipe import Recipe
from app.storage.calories import get_calorie, upsert_calorie
from tests.conftest import make_recipe


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield


def _recipe_with_calories(app):
    from app.storage.recipes import save_recipe

    with app.app_context():
        upsert_calorie("flour", "g", 100, 364)
        upsert_calorie("butter", "g", 100, 720)
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
    return recipe_id


class TestDetailPageBreakdownLink:
    @patch("app.routes.recipes.get_recipe")
    def test_shows_view_breakdown_link_when_calories_set(self, mock_get, client):
        mock_get.return_value = make_recipe(calories_per_serving=217.0)

        response = client.get("/recipes/abc123")

        assert response.status_code == 200
        assert b"View breakdown" in response.data
        assert b"/recipes/abc123/calories/breakdown" in response.data

    @patch("app.routes.recipes.get_recipe")
    def test_no_breakdown_link_when_calories_missing(self, mock_get, client):
        mock_get.return_value = make_recipe(calories_per_serving=None)

        response = client.get("/recipes/abc123")

        assert response.status_code == 200
        assert b"View breakdown" not in response.data


class TestBreakdownPage:
    def test_renders_rows_and_total(self, ctx, client, app):
        recipe_id = _recipe_with_calories(app)

        response = client.get(f"/recipes/{recipe_id}/calories/breakdown")

        assert response.status_code == 200
        assert b"Total per serving" in response.data
        assert b"flour" in response.data
        assert b"butter" in response.data
        # Reference info shown in the table row
        assert b"364" in response.data
        assert b"720" in response.data
        # Edit link for a row includes the ingredient scope + return_to=breakdown
        assert b"return_to=breakdown" in response.data
        assert b"name=flour" in response.data

    def test_redirects_to_edit_when_calories_missing(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "No cals",
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

        response = client.get(
            f"/recipes/{recipe_id}/calories/breakdown", follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["Location"] == f"/recipes/{recipe_id}/calories/edit"

    def test_negligible_ingredient_rendered_without_edit_button(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            upsert_calorie("flour", "g", 100, 364)
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "With salt",
                        "servings": "4",
                        "ingredients": [
                            {"quantity": "200", "unit": "g", "name": "flour"},
                            {"quantity": "1", "unit": "tsp", "name": "salt"},
                        ],
                        "steps": [{"step_number": 1, "instruction": "Mix."}],
                        "tags": [],
                    }
                ),
                "url",
                "",
            )

        response = client.get(f"/recipes/{recipe_id}/calories/breakdown")
        assert response.status_code == 200
        assert b"negligible" in response.data
        # There's one edit link (for flour), not two — salt row has none
        assert response.data.count(b"return_to=breakdown") == 1

    @patch("app.routes.recipes.get_recipe")
    def test_404_for_missing_recipe(self, mock_get, client):
        mock_get.return_value = None
        response = client.get("/recipes/999/calories/breakdown")
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
        response = client.get("/recipes/idea-1/calories/breakdown")
        assert response.status_code == 404


class TestSingleIngredientEditGet:
    def test_prefills_existing_entry(self, ctx, client, app):
        recipe_id = _recipe_with_calories(app)

        response = client.get(
            f"/recipes/{recipe_id}/calories/edit?name=flour&unit=g&return_to=breakdown"
        )

        assert response.status_code == 200
        # Only one fieldset — just the flour row
        assert response.data.count(b"<legend>") == 1
        assert b"flour" in response.data
        # Pre-filled values from the stored calorie entry
        assert b'value="100.0"' in response.data  # reference quantity
        assert b'value="364.0"' in response.data  # calories
        # Cancel link goes back to breakdown
        assert bytes(f"/recipes/{recipe_id}/calories/breakdown", "utf-8") in response.data

    def test_blank_when_no_existing_entry(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "New recipe",
                        "servings": "4",
                        "ingredients": [
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
            f"/recipes/{recipe_id}/calories/edit?name=eggs&return_to=breakdown"
        )
        assert response.status_code == 200
        assert response.data.count(b"<legend>") == 1
        # No pre-filled value attributes on the inputs
        assert b'name="reference_quantity" step="any" min="0.0001" placeholder="e.g. 100">' in response.data


class TestSingleIngredientEditPost:
    def test_save_redirects_to_breakdown(self, ctx, client, app):
        recipe_id = _recipe_with_calories(app)

        response = client.post(
            f"/recipes/{recipe_id}/calories/edit?name=flour&unit=g&return_to=breakdown",
            data={
                "name": ["flour"],
                "unit": ["g"],
                "reference_quantity": ["100"],
                "calories": ["400"],
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == (
            f"/recipes/{recipe_id}/calories/breakdown"
        )
        with app.app_context():
            entry = get_calorie("flour", "g")
            assert entry is not None and entry.calories == 400


class TestFullEditFlowUnchanged:
    """Regression: the existing all-missing calorie editor still redirects to detail."""

    def test_save_still_redirects_to_detail(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                Recipe.model_validate(
                    {
                        "title": "Plain",
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
                "calories": ["364"],
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == f"/recipes/{recipe_id}"
