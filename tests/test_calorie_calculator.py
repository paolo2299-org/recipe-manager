"""Tests for app.calories.calculator."""

import pytest

from app.calories.calculator import calculate_calories_per_serving, parse_quantity
from app.storage.calories import upsert_calorie


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

        recipe = {
            "record_type": "recipe",
            "servings": "4",
            "ingredients": [
                {"quantity": "200", "unit": "g", "name": "flour"},
                {"quantity": "2", "unit": None, "name": "eggs"},
            ],
        }

        # (200/100*364 + 2/1*70) / 4 = (728 + 140) / 4 = 217.0
        assert calculate_calories_per_serving(recipe) == 217.0

    def test_case_insensitive_matching(self, ctx):
        upsert_calorie("Flour", "G", 100, 400)
        recipe = {
            "record_type": "recipe",
            "servings": "2",
            "ingredients": [{"quantity": "100", "unit": "g", "name": "flour"}],
        }
        assert calculate_calories_per_serving(recipe) == 200.0

    def test_fraction_quantity(self, ctx):
        upsert_calorie("butter", "g", 100, 720)
        recipe = {
            "record_type": "recipe",
            "servings": "1",
            "ingredients": [{"quantity": "1 1/2", "unit": "g", "name": "butter"}],
        }
        assert calculate_calories_per_serving(recipe) == 10.8

    def test_unparseable_quantity_blocks(self, ctx):
        upsert_calorie("salt", "tsp", 1, 0)
        recipe = {
            "record_type": "recipe",
            "servings": "2",
            "ingredients": [{"quantity": "a pinch", "unit": "tsp", "name": "salt"}],
        }
        assert calculate_calories_per_serving(recipe) is None

    def test_missing_calorie_row_blocks(self, ctx):
        recipe = {
            "record_type": "recipe",
            "servings": "2",
            "ingredients": [{"quantity": "100", "unit": "g", "name": "quinoa"}],
        }
        assert calculate_calories_per_serving(recipe) is None

    def test_unparseable_servings_blocks(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        recipe = {
            "record_type": "recipe",
            "servings": "a few",
            "ingredients": [{"quantity": "100", "unit": "g", "name": "flour"}],
        }
        assert calculate_calories_per_serving(recipe) is None

    def test_idea_returns_none(self, ctx):
        recipe = {
            "record_type": "idea",
            "servings": "4",
            "ingredients": [{"quantity": "200", "unit": "g", "name": "flour"}],
        }
        assert calculate_calories_per_serving(recipe) is None

    def test_empty_ingredients_returns_none(self, ctx):
        recipe = {"record_type": "recipe", "servings": "4", "ingredients": []}
        assert calculate_calories_per_serving(recipe) is None

    def test_zero_servings_returns_none(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        recipe = {
            "record_type": "recipe",
            "servings": "0",
            "ingredients": [{"quantity": "100", "unit": "g", "name": "flour"}],
        }
        assert calculate_calories_per_serving(recipe) is None
