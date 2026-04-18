"""
Recipe extraction from an image using Anthropic Claude vision + tool use.

Usage:
    python extract_image_anthropic.py <image_path>

Requires:
    ANTHROPIC_API_KEY environment variable

Supports: JPEG, PNG, WebP, GIF images (local files).

The recipe schema is defined as a tool that Claude is forced to call,
guaranteeing structured output that matches the schema exactly.
"""

import base64
import io
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

# ---------------------------------------------------------------------------
# Image loading
# ---------------------------------------------------------------------------

SUPPORTED_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


MAX_RAW_BYTES = 3_932_160  # 5 MB base64 limit / 1.333 overhead
MAX_DIMENSION = 8000


def load_image(path: str) -> tuple[str, str]:
    """Read an image file and return (base64_data, media_type).

    Resizes and/or compresses the image if it exceeds API limits
    (8000px max dimension, 5 MB base64).
    """
    p = Path(path)
    media_type = SUPPORTED_MEDIA_TYPES.get(p.suffix.lower())
    if not media_type:
        raise ValueError(
            f"Unsupported image format '{p.suffix}'. "
            f"Supported: {sorted(SUPPORTED_MEDIA_TYPES)}"
        )
    raw = p.read_bytes()
    img = Image.open(io.BytesIO(raw)).convert("RGB")

    if max(img.size) > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
        print(f"Resized to {img.size[0]}x{img.size[1]}", file=sys.stderr)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    raw = buf.getvalue()
    media_type = "image/jpeg"

    if len(raw) > MAX_RAW_BYTES:
        print(
            f"Image is {len(raw):,} bytes — compressing to fit API limit...",
            file=sys.stderr,
        )
        for quality in range(75, 9, -10):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            raw = buf.getvalue()
            if len(raw) <= MAX_RAW_BYTES:
                print(f"Compressed to {len(raw):,} bytes (quality={quality})", file=sys.stderr)
                break
        else:
            raise RuntimeError("Could not compress image below 5 MB limit")

    data = base64.standard_b64encode(raw).decode("utf-8")
    return data, media_type


# ---------------------------------------------------------------------------
# Recipe schema (defined as an Anthropic tool)
# ---------------------------------------------------------------------------

EXTRACT_RECIPE_TOOL = {
    "name": "extract_recipe",
    "description": "Extract structured recipe information from an image of a recipe.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The name of the recipe.",
            },
            "description": {
                "type": "string",
                "description": "A brief description or introduction to the recipe.",
            },
            "servings": {
                "type": "string",
                "description": "Number of servings, e.g. '4' or 'Serves 4-6'.",
            },
            "prep_time": {
                "type": "string",
                "description": "Preparation time, e.g. '15 mins'.",
            },
            "cook_time": {
                "type": "string",
                "description": "Cooking time, e.g. '30 mins'.",
            },
            "total_time": {
                "type": "string",
                "description": "Total time from start to finish.",
            },
            "ingredients": {
                "type": "array",
                "description": "List of ingredients.",
                "items": {
                    "type": "object",
                    "properties": {
                        "quantity": {
                            "type": "string",
                            "description": "Amount, e.g. '2' or '1/2'.",
                        },
                        "unit": {
                            "type": "string",
                            "description": "Unit of measurement, e.g. 'cups', 'tbsp', 'g'.",
                        },
                        "name": {
                            "type": "string",
                            "description": "Ingredient name, e.g. 'plain flour'.",
                        },
                        "notes": {
                            "type": "string",
                            "description": "Optional prep notes, e.g. 'finely chopped'.",
                        },
                    },
                    "required": ["name"],
                },
            },
            "steps": {
                "type": "array",
                "description": "Ordered list of recipe steps.",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_number": {"type": "integer"},
                        "instruction": {"type": "string"},
                    },
                    "required": ["step_number", "instruction"],
                },
            },
            "tags": {
                "type": "array",
                "description": "Descriptive tags, e.g. ['vegetarian', 'quick'].",
                "items": {"type": "string"},
            },
        },
        "required": ["title", "ingredients", "steps"],
    },
}


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_recipe(image_path: str) -> dict:
    print(f"Loading image: {image_path}", file=sys.stderr)
    image_data, media_type = load_image(image_path)
    print(f"Loaded {len(image_data):,} chars (base64), media type: {media_type}", file=sys.stderr)

    client = anthropic.Anthropic()

    print("Calling Claude...", file=sys.stderr)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[EXTRACT_RECIPE_TOOL],
        # Force the model to call our tool rather than reply in prose.
        tool_choice={"type": "tool", "name": "extract_recipe"},
        messages=[
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
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_recipe":
            print(
                f"Done. Input tokens: {response.usage.input_tokens}, "
                f"output tokens: {response.usage.output_tokens}",
                file=sys.stderr,
            )
            return block.input

    raise RuntimeError("Model did not call the extract_recipe tool")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_image_anthropic.py <image_path>", file=sys.stderr)
        sys.exit(1)

    result = extract_recipe(sys.argv[1])
    print(json.dumps(result, indent=2))
