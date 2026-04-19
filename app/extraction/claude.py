"""Recipe extraction using Anthropic Claude."""

import json
import logging
from typing import Any

import anthropic

from .image import prepare_image
from .jina import fetch_via_jina
from .schema import EDIT_RECIPE_TOOL, EXTRACT_RECIPE_TOOL

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


def extract_from_url(url: str) -> dict[str, Any]:
    """Extract a recipe from a webpage URL via Jina Reader + Claude."""
    logger.info("Fetching %s via Jina Reader...", url)
    try:
        content = fetch_via_jina(url)
    except Exception as e:
        raise ExtractionError(f"Failed to fetch URL: {e}") from e

    logger.info("Fetched %d characters", len(content))

    try:
        return _call_claude([
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


def extract_from_image(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """Extract a recipe from an uploaded image via Claude vision."""
    logger.info("Preparing image: %s", filename)
    try:
        image_data, media_type = prepare_image(file_bytes, filename)
    except Exception as e:
        raise ExtractionError(f"Image processing failed: {e}") from e

    logger.info("Prepared %d chars (base64), media type: %s", len(image_data), media_type)

    try:
        return _call_claude([
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


def edit_recipe(recipe: dict[str, Any], instruction: str) -> dict[str, Any]:
    """Apply a natural-language edit to a structured recipe."""
    try:
        return _call_claude_tool(
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
                        f"Current recipe JSON:\n{json.dumps(recipe, indent=2, sort_keys=True)}\n\n"
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
