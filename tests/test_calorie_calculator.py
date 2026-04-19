"""Tests for app.calories.calculator."""

import pytest

from app.calories.calculator import calculate_calories_per_serving, parse_quantity
from app.schemas.recipe import Recipe
from app.storage.calories import upsert_calorie


def _recipe(record_type: str, servings: str, ingredients: list[dict]) -> Recipe:
    return Recipe.model_validate(
        {
            "record_type": record_type,
            "title": "T",
            "servings": servings,
            "ingredients": ingredients,
            "steps": [{"step_number": 1, "instruction": "Do it."}] if record_type == "recipe" else [],
            "tags": [],
        }
    )


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield


class TestParseQuantity:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("2", 2.0),
            ("2.5", 2.5),
            ("0.25", 0.25),
            ("1/2", 0.5),
            ("3/4", 0.75),
            ("1 1/2", 1.5),
            ("2 3/4", 2.75),
            (3, 3.0),
            (1.5, 1.5),
        ],
    )
    def test_parses(self, value, expected):
        assert parse_quantity(value) == expected

    @pytest.mark.parametrize(
        "value",
        [None, "", "   ", "4-6", "a pinch", "1/0", "1 2/0", "one", "1 2", True],
    )
    def test_returns_none(self, value):
        assert parse_quantity(value) is None


class TestCalculateCaloriesPerServing:
    def test_happy_path(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        upsert_calorie("eggs", None, 1, 70)

        recipe = _recipe(
            "recipe",
            "4",
            [
                {"quantity": "200", "unit": "g", "name": "flour"},
                {"quantity": "2", "unit": None, "name": "eggs"},
            ],
        )

        # (200/100*364 + 2/1*70) / 4 = (728 + 140) / 4 = 217.0
        assert calculate_calories_per_serving(recipe) == 217.0

    def test_case_insensitive_matching(self, ctx):
        upsert_calorie("Flour", "G", 100, 400)
        recipe = _recipe(
            "recipe",
            "2",
            [{"quantity": "100", "unit": "g", "name": "flour"}],
        )
        assert calculate_calories_per_serving(recipe) == 200.0

    def test_fraction_quantity(self, ctx):
        upsert_calorie("butter", "g", 100, 720)
        recipe = _recipe(
            "recipe",
            "1",
            [{"quantity": "1 1/2", "unit": "g", "name": "butter"}],
        )
        assert calculate_calories_per_serving(recipe) == 10.8

    def test_unparseable_quantity_blocks(self, ctx):
        upsert_calorie("cumin", "tsp", 1, 8)
        recipe = _recipe(
            "recipe",
            "2",
            [{"quantity": "a pinch", "unit": "tsp", "name": "cumin"}],
        )
        assert calculate_calories_per_serving(recipe) is None

    def test_missing_calorie_row_blocks(self, ctx):
        recipe = _recipe(
            "recipe",
            "2",
            [{"quantity": "100", "unit": "g", "name": "quinoa"}],
        )
        assert calculate_calories_per_serving(recipe) is None

    def test_unparseable_servings_blocks(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        recipe = _recipe(
            "recipe",
            "a few",
            [{"quantity": "100", "unit": "g", "name": "flour"}],
        )
        assert calculate_calories_per_serving(recipe) is None

    def test_idea_returns_none(self, ctx):
        recipe = _recipe(
            "idea",
            "4",
            [{"quantity": "200", "unit": "g", "name": "flour"}],
        )
        assert calculate_calories_per_serving(recipe) is None

    def test_zero_servings_returns_none(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        recipe = _recipe(
            "recipe",
            "0",
            [{"quantity": "100", "unit": "g", "name": "flour"}],
        )
        assert calculate_calories_per_serving(recipe) is None

    def test_negligible_ingredients_contribute_zero(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        recipe = _recipe(
            "recipe",
            "2",
            [
                {"quantity": "200", "unit": "g", "name": "flour"},
                {"quantity": "1", "unit": "tsp", "name": "salt"},
                {"quantity": "500", "unit": "ml", "name": "water"},
            ],
        )
        # Only flour contributes: (200/100 * 364) / 2 = 364.0
        assert calculate_calories_per_serving(recipe) == 364.0

    def test_negligible_ingredient_with_unparseable_quantity(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        recipe = _recipe(
            "recipe",
            "2",
            [
                {"quantity": "200", "unit": "g", "name": "flour"},
                {"quantity": "a pinch", "unit": None, "name": "salt"},
            ],
        )
        assert calculate_calories_per_serving(recipe) == 364.0

    def test_negligible_ingredient_name_is_case_insensitive(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        recipe = _recipe(
            "recipe",
            "2",
            [
                {"quantity": "200", "unit": "g", "name": "flour"},
                {"quantity": "1", "unit": "tsp", "name": "SALT"},
                {"quantity": "1", "unit": "tbsp", "name": "  Parsley  "},
            ],
        )
        assert calculate_calories_per_serving(recipe) == 364.0

    def test_recipe_with_only_negligible_ingredients_returns_zero(self, ctx):
        recipe = _recipe(
            "recipe",
            "2",
            [
                {"quantity": "500", "unit": "ml", "name": "water"},
                {"quantity": "1", "unit": "tsp", "name": "salt"},
            ],
        )
        assert calculate_calories_per_serving(recipe) == 0.0
