"""Tests for app.storage.calories."""

import pytest

from app.schemas.calorie import MissingCalorie
from app.schemas.recipe import Recipe
from app.storage.calories import get_calorie, list_missing_for_recipe, upsert_calorie


def _idea(ingredients: list[dict]) -> Recipe:
    return Recipe.model_validate(
        {
            "record_type": "idea",
            "title": "Test",
            "ingredients": ingredients,
            "steps": [],
            "tags": [],
        }
    )


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield


class TestUpsertCalorie:
    def test_insert_and_get(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        row = get_calorie("flour", "g")
        assert row is not None
        assert row.name == "flour"
        assert row.unit == "g"
        assert row.reference_quantity == 100
        assert row.calories == 364

    def test_case_insensitive_lookup(self, ctx):
        upsert_calorie("Flour", "G", 100, 364)
        assert get_calorie("FLOUR", "g") is not None
        assert get_calorie("  flour  ", " G ") is not None

    def test_update_on_conflict(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        upsert_calorie("FLOUR", "G", 100, 400)
        row = get_calorie("flour", "g")
        assert row is not None
        assert row.calories == 400

    def test_empty_unit_matches_none(self, ctx):
        upsert_calorie("egg", None, 1, 70)
        assert get_calorie("egg", None) is not None
        assert get_calorie("egg", "") is not None

    def test_unit_distinguishes_entries(self, ctx):
        upsert_calorie("sugar", "g", 100, 387)
        upsert_calorie("sugar", "tbsp", 1, 48)
        gram = get_calorie("sugar", "g")
        tbsp = get_calorie("sugar", "tbsp")
        assert gram is not None and gram.calories == 387
        assert tbsp is not None and tbsp.calories == 48

    def test_invalid_values_raise(self, ctx):
        with pytest.raises(ValueError):
            upsert_calorie("flour", "g", 0, 364)
        with pytest.raises(ValueError):
            upsert_calorie("flour", "g", 100, -1)
        with pytest.raises(ValueError):
            upsert_calorie("", "g", 100, 364)


class TestListMissingForRecipe:
    def test_returns_only_unresolved(self, ctx):
        upsert_calorie("flour", "g", 100, 364)
        recipe = _idea(
            ingredients=[
                {"quantity": "100", "unit": "g", "name": "flour"},
                {"quantity": "2", "unit": None, "name": "eggs"},
            ]
        )
        missing = list_missing_for_recipe(recipe)
        assert missing == [MissingCalorie(name="eggs", unit=None)]

    def test_dedupes_by_normalized_key(self, ctx):
        recipe = _idea(
            ingredients=[
                {"quantity": "100", "unit": "g", "name": "Flour"},
                {"quantity": "200", "unit": "G", "name": "flour"},
                {"quantity": "2", "name": "eggs"},
            ]
        )
        missing = list_missing_for_recipe(recipe)
        assert missing == [
            MissingCalorie(name="Flour", unit="g"),
            MissingCalorie(name="eggs", unit=None),
        ]

    def test_empty_ingredient_list_returns_empty(self, ctx):
        recipe = _idea(ingredients=[])
        assert list_missing_for_recipe(recipe) == []
