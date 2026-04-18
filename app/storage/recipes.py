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


def _normalize_required_string(value, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name.replace('_', ' ').capitalize()} is required")
    return value.strip()


def _normalize_optional_string(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def _normalize_ingredient(item: dict | str) -> dict:
    if isinstance(item, str):
        return {
            "quantity": None,
            "unit": None,
            "name": _normalize_required_string(item, "ingredient name"),
            "notes": None,
        }
    if not isinstance(item, dict):
        raise ValueError("Each ingredient must be a string or object")
    return {
        "quantity": _normalize_optional_string(item.get("quantity")),
        "unit": _normalize_optional_string(item.get("unit")),
        "name": _normalize_required_string(item.get("name"), "ingredient name"),
        "notes": _normalize_optional_string(item.get("notes")),
    }


def _normalize_step(item: dict | str, step_number: int) -> dict:
    if isinstance(item, str):
        instruction = item
    elif isinstance(item, dict):
        instruction = item.get("instruction")
    else:
        raise ValueError("Each step must be a string or object")
    return {
        "step_number": step_number,
        "instruction": _normalize_required_string(instruction, "step instruction"),
    }


def normalize_recipe_data(recipe_data: dict) -> dict:
    """Validate and normalize recipe data for previewing and persistence."""
    if not isinstance(recipe_data, dict):
        raise ValueError("Recipe data must be an object")

    ingredients = recipe_data.get("ingredients")
    steps = recipe_data.get("steps")
    tags = recipe_data.get("tags", [])

    if not isinstance(ingredients, list) or not ingredients:
        raise ValueError("At least one ingredient is required")
    if not isinstance(steps, list) or not steps:
        raise ValueError("At least one step is required")
    if not isinstance(tags, list):
        raise ValueError("Tags must be a list")

    return {
        "title": _normalize_required_string(recipe_data.get("title"), "title"),
        "description": _normalize_optional_string(recipe_data.get("description")),
        "servings": _normalize_optional_string(recipe_data.get("servings")),
        "prep_time": _normalize_optional_string(recipe_data.get("prep_time")),
        "cook_time": _normalize_optional_string(recipe_data.get("cook_time")),
        "total_time": _normalize_optional_string(recipe_data.get("total_time")),
        "ingredients": [_normalize_ingredient(item) for item in ingredients],
        "steps": [
            _normalize_step(item, step_number)
            for step_number, item in enumerate(steps, start=1)
        ],
        "tags": [
            normalized
            for normalized in (_normalize_optional_string(tag) for tag in tags)
            if normalized
        ],
    }


def _recipe_values(recipe_data: dict) -> tuple:
    normalized = normalize_recipe_data(recipe_data)
    return (
        normalized["title"],
        normalized["description"],
        normalized["servings"],
        normalized["prep_time"],
        normalized["cook_time"],
        normalized["total_time"],
        json.dumps(normalized["ingredients"]),
        json.dumps(normalized["steps"]),
        json.dumps(normalized["tags"]),
    )


def save_recipe(recipe_data: dict, source_type: str, source_ref: str) -> str:
    """Insert a recipe row. Returns the new ID as a string."""
    db = get_db()
    recipe_values = _recipe_values(recipe_data)
    cursor = db.execute(
        f"""
        INSERT INTO {TABLE} (
            title, description, servings, prep_time, cook_time, total_time,
            ingredients, steps, tags, source_type, source_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        recipe_values + (source_type, source_ref),
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


def update_recipe(recipe_id: str, recipe_data: dict) -> None:
    """Update a recipe row in place."""
    db = get_db()
    db.execute(
        f"""
        UPDATE {TABLE}
        SET title = ?,
            description = ?,
            servings = ?,
            prep_time = ?,
            cook_time = ?,
            total_time = ?,
            ingredients = ?,
            steps = ?,
            tags = ?,
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
