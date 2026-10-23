"""Recipe tools exposed over MCP."""

import json
from typing import Any, Callable

from app.schemas.recipe import Recipe
from app.storage.recipes import get_recipe, list_recipes

DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100


class ToolError(Exception):
    """A tool failed in a way the model should see (reported as isError)."""


def _summary(recipe: Recipe) -> dict[str, Any]:
    return {
        "id": recipe.id,
        "title": recipe.title,
        "record_type": recipe.record_type,
        "description": recipe.description,
        "tags": recipe.tags,
        "total_time": recipe.total_time,
    }


def _matches(recipe: Recipe, query: str) -> bool:
    haystack = [recipe.title, recipe.description or "", *recipe.tags]
    haystack.extend(ing.name for ing in recipe.ingredients)
    return query in " ".join(haystack).lower()


def search_recipes(arguments: dict[str, Any]) -> Any:
    query = arguments.get("query")
    if query is not None and not isinstance(query, str):
        raise ToolError("query must be a string")
    limit = arguments.get("limit", DEFAULT_SEARCH_LIMIT)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ToolError("limit must be a positive integer")
    limit = min(limit, MAX_SEARCH_LIMIT)

    needle = (query or "").strip().lower()
    recipes = list_recipes()
    if needle:
        recipes = [r for r in recipes if _matches(r, needle)]
    return {"recipes": [_summary(r) for r in recipes[:limit]]}


def get_recipe_tool(arguments: dict[str, Any]) -> Any:
    recipe_id = arguments.get("id")
    if not isinstance(recipe_id, str) or not recipe_id.strip():
        raise ToolError("id must be a non-empty string")
    recipe = get_recipe(recipe_id.strip())
    if recipe is None:
        raise ToolError(f"No recipe with id {recipe_id!r}")
    return recipe.model_dump(exclude={"created_at", "updated_at"})


TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_recipes",
        "title": "Search recipes",
        "description": (
            "Search saved recipes and recipe ideas by title, description, tag or "
            "ingredient. Omit query to list the most recent ones. Returns summaries; "
            "use get_recipe for full ingredients and steps."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Case-insensitive text to match."},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_SEARCH_LIMIT,
                    "description": f"Maximum results (default {DEFAULT_SEARCH_LIMIT}).",
                },
            },
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_recipe",
        "title": "Get recipe",
        "description": "Fetch one saved recipe, including ingredients and steps, by id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Recipe id from search_recipes."},
            },
            "required": ["id"],
        },
        "annotations": {"readOnlyHint": True},
    },
]

HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "search_recipes": search_recipes,
    "get_recipe": get_recipe_tool,
}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run a tool and wrap its result as an MCP CallToolResult."""
    handler = HANDLERS[name]
    try:
        result = handler(arguments)
    except ToolError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    return {
        "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
        "structuredContent": result,
        "isError": False,
    }
