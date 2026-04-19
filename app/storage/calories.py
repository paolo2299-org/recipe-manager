"""Calorie lookup table CRUD operations."""

import sqlite3
from typing import Any

from pydantic import ValidationError

from app.calories.negligible import is_negligible
from app.schemas.calorie import CalorieEntry, MissingCalorie
from app.schemas.recipe import RECORD_TYPE_IDEA, Ingredient, Recipe

from .db import get_db

TABLE = "calories"


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip().lower()


def _row_to_entry(row: sqlite3.Row) -> CalorieEntry:
    return CalorieEntry(
        name=row["name"],
        unit=row["unit"],
        reference_quantity=row["reference_quantity"],
        calories=row["calories"],
    )


def get_calorie(name: str, unit: str | None) -> CalorieEntry | None:
    """Fetch a calorie entry for a (name, unit) pair, case-insensitive."""
    name_key = _normalize_key(name)
    unit_key = _normalize_key(unit)
    if not name_key:
        return None
    db = get_db()
    row = db.execute(
        f"SELECT * FROM {TABLE} WHERE name_key = ? AND unit_key = ?",
        (name_key, unit_key),
    ).fetchone()
    return _row_to_entry(row) if row is not None else None


def upsert_calorie(
    name: str,
    unit: str | None,
    reference_quantity: float,
    calories: float,
) -> None:
    """Insert or update a calorie entry, keyed by the normalized (name, unit)."""
    try:
        entry = CalorieEntry(
            name=name,
            unit=unit,
            reference_quantity=reference_quantity,
            calories=calories,
        )
    except ValidationError as exc:
        errors = exc.errors()
        if errors:
            msg = str(errors[0].get("msg", ""))
            prefix = "Value error, "
            if msg.startswith(prefix):
                msg = msg[len(prefix):]
            raise ValueError(msg) from exc
        raise ValueError(str(exc)) from exc

    name_key = _normalize_key(entry.name)
    unit_key = _normalize_key(entry.unit)

    db = get_db()
    db.execute(
        f"""
        INSERT INTO {TABLE} (
            name, unit, name_key, unit_key, reference_quantity, calories
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(name_key, unit_key) DO UPDATE SET
            reference_quantity = excluded.reference_quantity,
            calories = excluded.calories,
            updated_at = datetime('now')
        """,
        (
            entry.name,
            entry.unit,
            name_key,
            unit_key,
            entry.reference_quantity,
            entry.calories,
        ),
    )
    db.commit()


def list_missing_for_recipe(recipe: Recipe) -> list[MissingCalorie]:
    """Return the unique (name, unit) pairs in a recipe with no calorie row.

    Deduplicated by normalized key, preserving the first-seen casing for display.
    """
    seen_keys: set[tuple[str, str]] = set()
    missing: list[MissingCalorie] = []
    for ingredient in recipe.ingredients:
        name = ingredient.name
        unit = ingredient.unit
        if is_negligible(name):
            continue
        name_key = _normalize_key(name)
        unit_key = _normalize_key(unit)
        dedupe_key = (name_key, unit_key)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        if get_calorie(name, unit) is None:
            missing.append(MissingCalorie(name=name, unit=unit))
    return missing


def list_unparseable_for_recipe(recipe: Recipe) -> list[tuple[int, Ingredient]]:
    """Return (index, ingredient) for non-negligible ingredients with an unparseable quantity.

    Calorie calculation short-circuits on any such ingredient, so the user needs to
    supply a usable quantity before the calorie editor can succeed.
    """
    # Local import to avoid a circular dependency (calculator imports from this module).
    from app.calories.calculator import parse_quantity

    unparseable: list[tuple[int, Ingredient]] = []
    for index, ingredient in enumerate(recipe.ingredients):
        if is_negligible(ingredient.name):
            continue
        if parse_quantity(ingredient.quantity) is None:
            unparseable.append((index, ingredient))
    return unparseable


def servings_needs_fix(recipe: Recipe) -> bool:
    """Return True if the recipe's servings value can't be used to compute per-serving calories."""
    # Local import to avoid a circular dependency (calculator imports from this module).
    from app.calories.calculator import parse_quantity

    if recipe.record_type == RECORD_TYPE_IDEA:
        return False
    servings = parse_quantity(recipe.servings)
    return servings is None or servings <= 0
