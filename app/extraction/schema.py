"""Claude tool schemas for recipe extraction and editing.

Tool input schemas are derived from Pydantic models in `app.schemas.recipe`
so the contract with Claude stays in lockstep with the in-process types.
"""

from typing import Any

from pydantic import BaseModel

from app.schemas.calorie import PrefilledCalories
from app.schemas.recipe import (
    ALLOWED_RECIPE_TAGS,
    EditedRecipe,
    ExtractedRecipe,
)

__all__ = [
    "ALLOWED_RECIPE_TAGS",
    "EDIT_RECIPE_TOOL",
    "EXTRACT_RECIPE_TOOL",
    "FILL_CALORIES_TOOL",
]


def _tool(name: str, description: str, model: type[BaseModel]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": model.model_json_schema(),
    }


EXTRACT_RECIPE_TOOL: dict[str, Any] = _tool(
    "extract_recipe",
    "Extract structured recipe information.",
    ExtractedRecipe,
)

EDIT_RECIPE_TOOL: dict[str, Any] = _tool(
    "edit_recipe",
    "Edit an existing structured recipe based on a natural language request.",
    EditedRecipe,
)

FILL_CALORIES_TOOL: dict[str, Any] = _tool(
    "fill_calories",
    (
        "Suggest a typical reference quantity and the calories in that amount "
        "for each ingredient provided. Return entries in the same order as the input."
    ),
    PrefilledCalories,
)
