"""Recipe CRUD operations backed by SQLite."""

import json
import sqlite3

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
    "save_recipe",
    "update_recipe",
]


def _row_to_recipe(row: sqlite3.Row) -> Recipe:
    data = dict(row)
    for field in _JSON_FIELDS:
        raw = data.get(field)
        data[field] = json.loads(raw) if raw else []
    data["id"] = str(data["id"])
    return Recipe.model_validate(data)


def _recipe_values(
    recipe: Recipe,
) -> tuple[str, str, str | None, str | None, str | None, str | None, str | None, str, str, str, float | None]:
    from app.calories.calculator import calculate_calories_per_serving

    calories_per_serving = calculate_calories_per_serving(recipe)
    return (
        recipe.record_type,
        recipe.title,
        recipe.description,
        recipe.servings,
        recipe.prep_time,
        recipe.cook_time,
        recipe.total_time,
        json.dumps([ing.model_dump() for ing in recipe.ingredients]),
        json.dumps([step.model_dump() for step in recipe.steps]),
        json.dumps(recipe.tags),
        calories_per_serving,
    )


def save_recipe(recipe: Recipe, source_type: str, source_ref: str) -> str:
    """Insert a recipe row. Returns the new ID as a string."""
    db = get_db()
    cursor = db.execute(
        f"""
        INSERT INTO {TABLE} (
            record_type, title, description, servings, prep_time, cook_time, total_time,
            ingredients, steps, tags, calories_per_serving, source_type, source_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _recipe_values(recipe) + (source_type, source_ref),
    )
    db.commit()
    return str(cursor.lastrowid)


def get_recipe(recipe_id: str) -> Recipe | None:
    """Fetch a single recipe by ID. Returns None if not found."""
    db = get_db()
    row = db.execute(
        f"SELECT * FROM {TABLE} WHERE id = ?", (recipe_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_recipe(row)


def list_recipes(limit: int | None = None) -> list[Recipe]:
    """List recipes ordered by creation date, newest first."""
    db = get_db()
    query = f"SELECT * FROM {TABLE} ORDER BY created_at DESC, id DESC"
    params: tuple[int, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    rows = db.execute(query, params).fetchall()
    return [_row_to_recipe(r) for r in rows]


def update_recipe(recipe_id: str, recipe: Recipe) -> None:
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
        _recipe_values(recipe) + (recipe_id,),
    )
    db.commit()


def delete_recipe(recipe_id: str) -> None:
    """Delete a recipe by ID."""
    db = get_db()
    db.execute(f"DELETE FROM {TABLE} WHERE id = ?", (recipe_id,))
    db.commit()
