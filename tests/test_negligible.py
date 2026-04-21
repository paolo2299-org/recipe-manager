"""Tests for the negligible-ingredient allow-list."""

from app.calories.negligible import is_negligible


def test_common_low_signal_seasonings_are_negligible():
    assert is_negligible("Kosher Salt") is True
    assert is_negligible(" freshly ground black pepper ") is True
    assert is_negligible("dried parsley") is True
    assert is_negligible("bay leaves") is True
    assert is_negligible("warm water") is True


def test_material_ingredients_are_not_treated_as_negligible():
    assert is_negligible("garlic") is False
    assert is_negligible("onion") is False
    assert is_negligible("olive oil") is False
