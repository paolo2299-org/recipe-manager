"""Tests for the calorie-editing routes."""

from unittest.mock import patch

import pytest

from app.storage.calories import get_calorie, upsert_calorie
from tests.conftest import SAMPLE_RECIPE_DB


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield


class TestDetailPageCalories:
    @patch("app.routes.recipes.get_recipe")
    def test_shows_add_calorie_link_when_null(self, mock_get, client):
        mock_get.return_value = {**SAMPLE_RECIPE_DB, "calories_per_serving": None}

        response = client.get("/recipes/abc123")

        assert response.status_code == 200
        assert b"Add calorie information" in response.data
        assert b"/recipes/abc123/calories/edit" in response.data

    @patch("app.routes.recipes.get_recipe")
    def test_shows_value_when_set(self, mock_get, client):
        mock_get.return_value = {**SAMPLE_RECIPE_DB, "calories_per_serving": 217.0}

        response = client.get("/recipes/abc123")

        assert response.status_code == 200
        assert b"Calories per serving" in response.data
        assert b"217.0" in response.data

    @patch("app.routes.recipes.get_recipe")
    def test_hidden_for_ideas(self, mock_get, client):
        mock_get.return_value = {
            "id": "idea-1",
            "record_type": "idea",
            "title": "Chicken shawarma bowls",
            "description": None,
            "servings": None,
            "prep_time": None,
            "cook_time": None,
            "total_time": None,
            "ingredients": [],
            "steps": [],
            "tags": ["dinner"],
            "source_type": "manual",
            "source_ref": "",
            "calories_per_serving": None,
            "created_at": None,
            "updated_at": None,
        }

        response = client.get("/recipes/idea-1")

        assert response.status_code == 200
        assert b"Add calorie information" not in response.data
        assert b"Calories per serving" not in response.data


class TestEditCaloriesGet:
    def test_lists_missing_ingredients(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                {
                    "title": "Minimal",
                    "servings": "4",
                    "ingredients": [
                        {"quantity": "200", "unit": "g", "name": "flour"},
                        {"quantity": "2", "name": "eggs"},
                    ],
                    "steps": [{"step_number": 1, "instruction": "Mix."}],
                    "tags": [],
                },
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
                {
                    "title": "Roux",
                    "servings": "4",
                    "ingredients": [
                        {"quantity": "100", "unit": "g", "name": "flour"},
                        {"quantity": "100", "unit": "g", "name": "butter"},
                    ],
                    "steps": [{"step_number": 1, "instruction": "Cook."}],
                    "tags": [],
                },
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
        mock_get.return_value = {
            "id": "idea-1",
            "record_type": "idea",
            "title": "Idea",
            "ingredients": [],
            "steps": [],
            "tags": [],
        }
        response = client.get("/recipes/idea-1/calories/edit")
        assert response.status_code == 404


class TestSaveCalories:
    def test_upserts_and_recomputes(self, ctx, client, app):
        from app.storage.recipes import get_recipe, save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                {
                    "title": "Shortbread",
                    "servings": "12",
                    "ingredients": [
                        {"quantity": "200", "unit": "g", "name": "flour"},
                        {"quantity": "100", "unit": "g", "name": "butter"},
                    ],
                    "steps": [{"step_number": 1, "instruction": "Mix."}],
                    "tags": [],
                },
                "url",
                "",
            )
            assert get_recipe(recipe_id)["calories_per_serving"] is None

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
            assert get_calorie("flour", "g")["calories"] == 364
            assert get_calorie("butter", "g")["calories"] == 720
            stored = get_recipe(recipe_id)
            # (200/100*364 + 100/100*720) / 12 = 120.67
            assert stored["calories_per_serving"] == 120.7

    def test_blank_rows_are_skipped(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                {
                    "title": "Partial",
                    "servings": "4",
                    "ingredients": [
                        {"quantity": "200", "unit": "g", "name": "flour"},
                        {"quantity": "2", "name": "eggs"},
                    ],
                    "steps": [{"step_number": 1, "instruction": "Mix."}],
                    "tags": [],
                },
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
            assert get_calorie("flour", "g")["calories"] == 364
            assert get_calorie("eggs", None) is None

    def test_partial_row_shows_error(self, ctx, client, app):
        from app.storage.recipes import save_recipe

        with app.app_context():
            recipe_id = save_recipe(
                {
                    "title": "Partial",
                    "servings": "4",
                    "ingredients": [
                        {"quantity": "200", "unit": "g", "name": "flour"},
                    ],
                    "steps": [{"step_number": 1, "instruction": "Mix."}],
                    "tags": [],
                },
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
