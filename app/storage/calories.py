"""Calorie lookup table CRUD operations."""

import sqlite3
from typing import Any, Mapping

from pydantic import ValidationError

from app.schemas.calorie import CalorieEntry

from .db import get_db

TABLE = "calories"


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip().lower()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data: dict[str, Any] = dict(row)
    data["id"] = str(data["id"])
    return data


def get_calorie(name: str, unit: str | None) -> dict[str, Any] | None:
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


def list_missing_for_recipe(recipe: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the unique (name, unit) pairs in a recipe with no calorie row.

    Deduplicated by normalized key, preserving the first-seen casing for display.
    """
    ingredients = recipe.get("ingredients") or []
    seen_keys: set[tuple[str, str]] = set()
    missing: list[dict[str, Any]] = []
    for ingredient in ingredients:
        if not isinstance(ingredient, Mapping):
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
            missing.append(
                {
                    "name": name.strip(),
                    "unit": unit.strip() if isinstance(unit, str) and unit.strip() else None,
                }
            )
    return missing
