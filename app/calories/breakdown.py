"""Per-ingredient breakdown of a recipe's calorie contributions."""

from app.calories.calculator import parse_quantity
from app.calories.negligible import is_negligible
from app.schemas.calorie import BreakdownRow
from app.schemas.recipe import Recipe
from app.storage.calories import get_calorie


def build_breakdown(recipe: Recipe) -> list[BreakdownRow]:
    """Return a row per ingredient in the recipe with its per-serving calorie contribution.

    Duplicate (name, unit) pairs are rendered as separate rows so the list matches
    the recipe's ingredients in order. `per_serving_calories` is None when the
    ingredient is negligible, has an unparseable quantity, or has no calorie row
    (defensive — this is not expected when the recipe has a stored total).
    """
    servings = parse_quantity(recipe.servings)
    if servings is not None and servings <= 0:
        servings = None

    rows: list[BreakdownRow] = []
    for ingredient in recipe.ingredients:
        if is_negligible(ingredient.name):
            rows.append(
                BreakdownRow(
                    name=ingredient.name,
                    unit=ingredient.unit,
                    quantity=ingredient.quantity,
                    per_serving_calories=None,
                    reference=None,
                    is_negligible=True,
                )
            )
            continue

        reference = get_calorie(ingredient.name, ingredient.unit)
        quantity = parse_quantity(ingredient.quantity)

        per_serving: float | None = None
        if (
            servings is not None
            and quantity is not None
            and reference is not None
            and reference.reference_quantity
        ):
            per_serving = round(
                quantity / reference.reference_quantity * reference.calories / servings,
                1,
            )

        rows.append(
            BreakdownRow(
                name=ingredient.name,
                unit=ingredient.unit,
                quantity=ingredient.quantity,
                per_serving_calories=per_serving,
                reference=reference,
                is_negligible=False,
            )
        )

    return rows
