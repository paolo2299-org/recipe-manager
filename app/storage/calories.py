"""Calorie lookup table CRUD operations."""

from .db import get_db

TABLE = "calories"


def _normalize_key(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip().lower()


def _row_to_dict(row) -> dict:
    data = dict(row)
    data["id"] = str(data["id"])
    return data


def get_calorie(name: str, unit: str | None) -> dict | None:
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
    return _row_to_dict(row) if row is not None else None


def upsert_calorie(
    name: str,
    unit: str | None,
    reference_quantity: float,
    calories: float,
) -> None:
    """Insert or update a calorie entry, keyed by the normalized (name, unit)."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Calorie name is required")
    try:
        reference_quantity = float(reference_quantity)
        calories = float(calories)
    except (TypeError, ValueError) as exc:
        raise ValueError("Reference quantity and calories must be numeric") from exc
    if reference_quantity <= 0:
        raise ValueError("Reference quantity must be greater than zero")
    if calories < 0:
        raise ValueError("Calories must be zero or greater")

    trimmed_name = name.strip()
    trimmed_unit = unit.strip() if isinstance(unit, str) and unit.strip() else None
    name_key = _normalize_key(trimmed_name)
    unit_key = _normalize_key(trimmed_unit)

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
        (trimmed_name, trimmed_unit, name_key, unit_key, reference_quantity, calories),
    )
    db.commit()


def list_missing_for_recipe(recipe: dict) -> list[dict]:
    """Return the unique (name, unit) pairs in a recipe with no calorie row.

    Deduplicated by normalized key, preserving the first-seen casing for display.
    """
    ingredients = recipe.get("ingredients") or []
    seen_keys: set[tuple[str, str]] = set()
    missing: list[dict] = []
    for ingredient in ingredients:
        if not isinstance(ingredient, dict):
            continue
        name = ingredient.get("name")
        unit = ingredient.get("unit")
        if not isinstance(name, str) or not name.strip():
            continue
        name_key = _normalize_key(name)
        unit_key = _normalize_key(unit)
        dedupe_key = (name_key, unit_key)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        if get_calorie(name, unit) is None:
            missing.append({"name": name.strip(), "unit": unit.strip() if isinstance(unit, str) and unit.strip() else None})
    return missing
