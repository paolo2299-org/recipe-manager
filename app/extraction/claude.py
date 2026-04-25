"""Recipe extraction using Anthropic Claude."""

import json
import logging
from typing import Any

import anthropic
from pydantic import ValidationError

from app.schemas.calorie import CalorieEntry, MissingCalorie, PrefilledCalories
from app.schemas.recipe import EditedRecipe, Recipe

from .image import prepare_image
from .jina import fetch_via_jina
from .schema import EDIT_RECIPE_TOOL, EXTRACT_RECIPE_TOOL, FILL_CALORIES_TOOL

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Base class for extraction failures."""
    pass


def _call_claude_tool(
    messages: list[dict[str, Any]], tool: dict[str, Any]
) -> dict[str, Any]:
    """Send messages to Claude with forced tool use and return the tool payload."""
    tool_name = tool["name"]
    client = anthropic.Anthropic()
    response = client.messages.create(  # type: ignore[call-overload]
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=messages,
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            logger.info(
                "Claude tool %s complete. Input tokens: %d, output tokens: %d",
                tool_name,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            payload = block.input
            if not isinstance(payload, dict):
                raise ExtractionError(
                    f"Tool {tool_name} returned a non-object payload"
                )
            return payload

    raise ExtractionError(f"Model did not call the {tool_name} tool")


def _call_claude(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Invoke the extract_recipe tool and return its raw payload."""
    return _call_claude_tool(messages, EXTRACT_RECIPE_TOOL)


def _parse_recipe(payload: dict[str, Any]) -> Recipe:
    try:
        return Recipe.model_validate(payload)
    except ValidationError as exc:
        raise ExtractionError(f"Claude returned invalid recipe data: {exc}") from exc


def extract_from_url(url: str) -> Recipe:
    """Extract a recipe from a webpage URL via Jina Reader + Claude."""
    logger.info("Fetching %s via Jina Reader...", url)
    try:
        content = fetch_via_jina(url)
    except Exception as e:
        raise ExtractionError(f"Failed to fetch URL: {e}") from e

    logger.info("Fetched %d characters", len(content))

    try:
        payload = _call_claude([
            {
                "role": "user",
                "content": (
                    "Extract the recipe from the following webpage content "
                    "and call the extract_recipe tool with the structured data.\n\n"
                    f"{content}"
                ),
            }
        ])
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"Claude API call failed: {e}") from e

    return _parse_recipe(payload)


def extract_from_image(file_bytes: bytes, filename: str) -> Recipe:
    """Extract a recipe from an uploaded image via Claude vision."""
    logger.info("Preparing image: %s", filename)
    try:
        image_data, media_type = prepare_image(file_bytes, filename)
    except Exception as e:
        raise ExtractionError(f"Image processing failed: {e}") from e

    logger.info("Prepared %d chars (base64), media type: %s", len(image_data), media_type)

    try:
        payload = _call_claude([
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is an image of a recipe — it may be a screenshot or a photo "
                            "of a recipe book. Carefully read all visible text, including any "
                            "text that is at an angle, partially obscured, or in uneven lighting. "
                            "Extract the complete recipe and call the extract_recipe tool with "
                            "the structured data."
                        ),
                    },
                ],
            }
        ])
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"Claude API call failed: {e}") from e

    return _parse_recipe(payload)


def extract_from_text(content: str, source_label: str) -> Recipe:
    """Extract a recipe from user-supplied plain text via Claude."""
    logger.info(
        "Extracting recipe from text (%s, %d chars)", source_label, len(content)
    )

    try:
        payload = _call_claude([
            {
                "role": "user",
                "content": (
                    "The following is recipe text supplied by the user (typed "
                    "directly or read from a .txt/.md file). Extract the recipe "
                    "and call the extract_recipe tool with the structured data. "
                    "If the text contains commentary, headings, or unrelated "
                    "material, ignore it and focus only on the recipe.\n\n"
                    f"{content}"
                ),
            }
        ])
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"Claude API call failed: {e}") from e

    return _parse_recipe(payload)


def edit_recipe(recipe: Recipe, instruction: str) -> EditedRecipe:
    """Apply a natural-language edit to a structured recipe."""
    recipe_json = json.dumps(recipe.model_dump(mode="json"), indent=2, sort_keys=True)
    try:
        payload = _call_claude_tool(
            [
                {
                    "role": "user",
                    "content": (
                        "You are editing an existing structured recipe. Apply the user's "
                        "request to the recipe and call the edit_recipe tool with the full "
                        "updated recipe, a short change summary, and any warnings.\n\n"
                        "Rules:\n"
                        "- Preserve all fields that are not affected by the request.\n"
                        "- Make the smallest reasonable change.\n"
                        "- Do not invent new details unless needed to fulfill the request.\n"
                        "- Keep the recipe valid and complete.\n"
                        "- Renumber steps sequentially if they change.\n"
                        "- If the request is ambiguous, make the safest reasonable choice "
                        "and explain it in warnings.\n\n"
                        f"Current recipe JSON:\n{recipe_json}\n\n"
                        f"User request:\n{instruction}"
                    ),
                }
            ],
            EDIT_RECIPE_TOOL,
        )
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"Claude API call failed: {e}") from e

    try:
        return EditedRecipe.model_validate(payload)
    except ValidationError as exc:
        raise ExtractionError(f"Claude returned invalid edit payload: {exc}") from exc


def prefill_calories(missing: list[MissingCalorie]) -> list[CalorieEntry]:
    """Ask Claude for a reference quantity and calorie estimate per ingredient.

    Entries are returned in the same order as the input.
    """
    if not missing:
        return []

    items = [{"name": item.name, "unit": item.unit} for item in missing]
    items_json = json.dumps(items, indent=2)

    try:
        payload = _call_claude_tool(
            [
                {
                    "role": "user",
                    "content": (
                        "You are estimating calorie information for recipe ingredients. "
                        "For each item below, suggest a typical reference quantity and the "
                        "calories in that amount, then call the fill_calories tool.\n\n"
                        "Rules:\n"
                        "- Return one entry per input item, in the same order.\n"
                        "- Copy the `name` exactly as provided.\n"
                        "- Copy the `unit` exactly as provided on every entry, including "
                        "  leaving it null when the input unit is null. Do NOT invent a unit "
                        "  or change the unit — the caller keys off this value downstream.\n"
                        "- A null unit means the ingredient is counted in whole items (e.g. "
                        "  '2 eggs' -> unit=null, think 'each'). For null-unit items set "
                        "  reference_quantity to a count of whole items (usually 1, meaning "
                        "  'one whole egg') and set calories to the calories in that count.\n"
                        "- When a unit is provided, the reference_quantity must be expressed "
                        "  in that unit (e.g. unit='g' -> reference_quantity=100 meaning 100 g, "
                        "  unit='tbsp' -> reference_quantity=1 meaning 1 tbsp).\n"
                        "- reference_quantity must be > 0; calories must be >= 0.\n"
                        "- Prefer round, commonly-used reference amounts (100 g, 1 whole egg, "
                        "  1 tbsp, 1 cup, etc.).\n"
                        "- Do your best estimate — the user will review and can edit every row.\n\n"
                        f"Ingredients:\n{items_json}"
                    ),
                }
            ],
            FILL_CALORIES_TOOL,
        )
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"Claude API call failed: {e}") from e

    try:
        return PrefilledCalories.model_validate(payload).entries
    except ValidationError as exc:
        raise ExtractionError(
            f"Claude returned invalid calorie suggestions: {exc}"
        ) from exc
