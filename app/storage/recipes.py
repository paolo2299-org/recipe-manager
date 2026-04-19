"""Recipe CRUD operations backed by SQLite."""

import json
import sqlite3
from typing import Any, Mapping

from pydantic import ValidationError

from app.schemas.recipe import RECORD_TYPE_IDEA, RECORD_TYPE_RECIPE, Recipe

from .db import get_db

TABLE = "recipes"

_JSON_FIELDS = ("ingredients", "steps", "tags")

__all__ = [
    "RECORD_TYPE_IDEA",
    "RECORD_TYPE_RECIPE",
    "delete_recipe",
    "get_recipe",
    "list_recipes",
    "normalize_recipe_data",
    "save_recipe",
    "update_recipe",
]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data: dict[str, Any] = dict(row)
    for field in _JSON_FIELDS:
        raw = data.get(field)
        data[field] = json.loads(raw) if raw else []
    data["id"] = str(data["id"])
    return data


def normalize_recipe_data(recipe_data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize recipe data for previewing and persistence."""
    if not isinstance(recipe_data, Mapping):
        raise ValueError("Recipe data must be an object")
    try:
        recipe = Recipe.model_validate(dict(recipe_data))
    except ValidationError as exc:
        errors = exc.errors()
        if errors:
            msg = str(errors[0].get("msg", ""))
            prefix = "Value error, "
            if msg.startswith(prefix):
                msg = msg[len(prefix):]
            raise ValueError(msg) from exc
        raise ValueError(str(exc)) from exc
    return recipe.model_dump()


def _recipe_values(
    recipe_data: Mapping[str, Any]
) -> tuple[str, str, str | None, str | None, str | None, str | None, str | None, str, str, str, float | None]:
    from app.calories.calculator import calculate_calories_per_serving

    normalized = normalize_recipe_data(recipe_data)
    calories_per_serving = calculate_calories_per_serving(normalized)
    return (
        normalized["record_type"],
        normalized["title"],
        normalized["description"],
        normalized["servings"],
        normalized["prep_time"],
        normalized["cook_time"],
        normalized["total_time"],
        json.dumps(normalized["ingredients"]),
        json.dumps(normalized["steps"]),
        json.dumps(normalized["tags"]),
        calories_per_serving,
    )


def save_recipe(
    recipe_data: Mapping[str, Any], source_type: str, source_ref: str
) -> str:
    """Insert a recipe row. Returns the new ID as a string."""
    db = get_db()
    recipe_values = _recipe_values(recipe_data)
    cursor = db.execute(
        f"""
        INSERT INTO {TABLE} (
            record_type, title, description, servings, prep_time, cook_time, total_time,
            ingredients, steps, tags, calories_per_serving, source_type, source_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        recipe_values + (source_type, source_ref),
    )
    db.commit()
    return str(cursor.lastrowid)


def get_recipe(recipe_id: str) -> dict[str, Any] | None:
    """Fetch a single recipe by ID. Returns None if not found."""
    db = get_db()
    row = db.execute(
        f"SELECT * FROM {TABLE} WHERE id = ?", (recipe_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_recipes(limit: int = 50) -> list[dict[str, Any]]:
    """List recipes ordered by creation date, newest first."""
    db = get_db()
    rows = db.execute(
        f"SELECT * FROM {TABLE} ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_recipe(recipe_id: str, recipe_data: Mapping[str, Any]) -> None:
    """Update a recipe row in place."""
    db = get_db()
    db.execute(
        f"""
        UPDATE {TABLE}
        SET record_type = ?,
            title = ?,
            description = ?,
            servings = ?,
            prep_time = ?,
            cook_time = ?,
            total_time = ?,
            ingredients = ?,
            steps = ?,
            tags = ?,
            calories_per_serving = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        _recipe_values(recipe_data) + (recipe_id,),
    )
    db.commit()


def delete_recipe(recipe_id: str) -> None:
    """Delete a recipe by ID."""
    db = get_db()
    db.execute(f"DELETE FROM {TABLE} WHERE id = ?", (recipe_id,))
    db.commit()
