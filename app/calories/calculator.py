"""Per-serving calorie calculation for recipes."""

from typing import Any, Mapping

from app.schemas.recipe import RECORD_TYPE_IDEA
from app.storage.calories import get_calorie


def parse_quantity(value: Any) -> float | None:
    """Parse a quantity string into a float.

    Accepts integers, decimals, simple fractions ("1/2"), and mixed fractions
    ("1 1/2"). Returns None for empty input, ranges ("4-6"), or anything else.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    parts = text.split()
    try:
        if len(parts) == 2:
            whole = int(parts[0])
            fraction = parts[1]
            if "/" not in fraction:
                return None
            num, denom = fraction.split("/", 1)
            denom_value = int(denom)
            if denom_value == 0:
                return None
            sign = -1 if whole < 0 else 1
            return whole + sign * int(num) / denom_value
        if len(parts) == 1:
            token = parts[0]
            if "/" in token:
                num, denom = token.split("/", 1)
                denom_value = int(denom)
                if denom_value == 0:
                    return None
                return int(num) / denom_value
            return float(token)
    except ValueError:
        return None
    return None


def calculate_calories_per_serving(recipe: Mapping[str, Any]) -> float | None:
    """Compute the per-serving calorie count, or None if the data is incomplete."""
    if recipe.get("record_type") == RECORD_TYPE_IDEA:
        return None

    ingredients = recipe.get("ingredients") or []
    if not ingredients:
        return None

    servings = parse_quantity(recipe.get("servings"))
    if servings is None or servings <= 0:
        return None

    total = 0.0
    for ingredient in ingredients:
        if not isinstance(ingredient, Mapping):
            return None
        quantity = parse_quantity(ingredient.get("quantity"))
        if quantity is None:
            return None
        name = ingredient.get("name")
        if not isinstance(name, str):
            return None
        unit = ingredient.get("unit")
        if unit is not None and not isinstance(unit, str):
            return None
        calorie_row = get_calorie(name, unit)
        if calorie_row is None:
            return None
        reference = calorie_row["reference_quantity"]
        if not reference:
            return None
        total += quantity / reference * calorie_row["calories"]

    return round(total / servings, 1)
