"""Tests for the per-ingredient calorie breakdown helper."""

import pytest

from app.calories.breakdown import build_breakdown
from app.schemas.recipe import Recipe
from app.storage.calories import upsert_calorie


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield


def test_rows_for_normal_and_negligible_and_duplicates(ctx):
    upsert_calorie("flour", "g", 100, 364)
    upsert_calorie("butter", "g", 100, 720)
    recipe = Recipe.model_validate(
        {
            "title": "Mixed",
            "servings": "4",
            "ingredients": [
                {"quantity": "200", "unit": "g", "name": "flour"},
                {"quantity": "100", "unit": "g", "name": "butter"},
                {"quantity": "50", "unit": "g", "name": "flour"},  # duplicate
                {"quantity": "1", "unit": "tsp", "name": "salt"},  # negligible
            ],
            "steps": [{"step_number": 1, "instruction": "Mix."}],
            "tags": [],
        }
    )

    rows = build_breakdown(recipe)

    assert len(rows) == 4
    # Flour 200g: 200/100 * 364 / 4 = 182.0
    assert rows[0].per_serving_calories == 182.0
    assert rows[0].reference is not None
    # Butter 100g: 100/100 * 720 / 4 = 180.0
    assert rows[1].per_serving_calories == 180.0
    # Flour 50g duplicate: 50/100 * 364 / 4 = 45.5
    assert rows[2].per_serving_calories == 45.5
    # Salt is negligible
    assert rows[3].is_negligible is True
    assert rows[3].per_serving_calories is None
    assert rows[3].reference is None


def test_row_with_no_calorie_data_shows_none(ctx):
    recipe = Recipe.model_validate(
        {
            "title": "No data",
            "servings": "4",
            "ingredients": [
                {"quantity": "2", "name": "eggs"},
            ],
            "steps": [{"step_number": 1, "instruction": "Mix."}],
            "tags": [],
        }
    )

    rows = build_breakdown(recipe)

    assert len(rows) == 1
    assert rows[0].is_negligible is False
    assert rows[0].reference is None
    assert rows[0].per_serving_calories is None


def test_row_with_unparseable_quantity_shows_none(ctx):
    upsert_calorie("oil", "tbsp", 1, 120)
    recipe = Recipe.model_validate(
        {
            "title": "Range quantity",
            "servings": "4",
            "ingredients": [
                {"quantity": "3-4", "unit": "tbsp", "name": "oil"},
            ],
            "steps": [{"step_number": 1, "instruction": "Mix."}],
            "tags": [],
        }
    )

    rows = build_breakdown(recipe)

    assert len(rows) == 1
    assert rows[0].reference is not None
    assert rows[0].per_serving_calories is None


def test_per_serving_sum_matches_stored_total(ctx):
    upsert_calorie("flour", "g", 100, 364)
    upsert_calorie("butter", "g", 100, 720)
    recipe = Recipe.model_validate(
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
    )

    rows = build_breakdown(recipe)

    # Sum of per-row contributions should be close to (200/100*364 + 100/100*720) / 12 = 120.666...
    total = sum(r.per_serving_calories or 0 for r in rows)
    assert abs(total - 120.7) < 0.2
