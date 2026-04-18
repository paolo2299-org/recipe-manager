"""Recipe CRUD operations backed by SQLite."""

import json

from .db import get_db

TABLE = "recipes"

_JSON_FIELDS = ("ingredients", "steps", "tags")
_OPTIONAL_FIELDS = ("description", "servings", "prep_time", "cook_time", "total_time")


def _row_to_dict(row) -> dict:
    data = dict(row)
    for field in _JSON_FIELDS:
        data[field] = json.loads(data[field]) if data.get(field) else []
    data["id"] = str(data["id"])
    return data


def save_recipe(recipe_data: dict, source_type: str, source_ref: str) -> str:
    """Insert a recipe row. Returns the new ID as a string."""
    db = get_db()
    cursor = db.execute(
        f"""
        INSERT INTO {TABLE} (
            title, description, servings, prep_time, cook_time, total_time,
            ingredients, steps, tags, source_type, source_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recipe_data["title"],
            recipe_data.get("description"),
            recipe_data.get("servings"),
            recipe_data.get("prep_time"),
            recipe_data.get("cook_time"),
            recipe_data.get("total_time"),
            json.dumps(recipe_data.get("ingredients", [])),
            json.dumps(recipe_data.get("steps", [])),
            json.dumps(recipe_data.get("tags", [])),
            source_type,
            source_ref,
        ),
    )
    db.commit()
    return str(cursor.lastrowid)


def get_recipe(recipe_id: str) -> dict | None:
    """Fetch a single recipe by ID. Returns None if not found."""
    db = get_db()
    row = db.execute(
        f"SELECT * FROM {TABLE} WHERE id = ?", (recipe_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_recipes(limit: int = 50) -> list[dict]:
    """List recipes ordered by creation date, newest first."""
    db = get_db()
    rows = db.execute(
        f"SELECT * FROM {TABLE} ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_recipe(recipe_id: str) -> None:
    """Delete a recipe by ID."""
    db = get_db()
    db.execute(f"DELETE FROM {TABLE} WHERE id = ?", (recipe_id,))
    db.commit()
