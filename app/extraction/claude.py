"""Recipe extraction using Anthropic Claude."""

import logging

import anthropic

from .image import prepare_image
from .jina import fetch_via_jina
from .schema import EXTRACT_RECIPE_TOOL

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Base class for extraction failures."""
    pass


def _call_claude(messages: list[dict]) -> dict:
    """Send messages to Claude with forced tool use and return the extracted recipe."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[EXTRACT_RECIPE_TOOL],
        tool_choice={"type": "tool", "name": "extract_recipe"},
        messages=messages,
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_recipe":
            logger.info(
                "Extraction complete. Input tokens: %d, output tokens: %d",
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            return block.input

    raise ExtractionError("Model did not call the extract_recipe tool")


def extract_from_url(url: str) -> dict:
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


def extract_from_image(file_bytes: bytes, filename: str) -> dict:
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
