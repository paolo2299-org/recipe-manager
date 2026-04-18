"""
Recipe extraction using Jina Reader + Anthropic Claude (tool use).

Usage:
    python extract_anthropic.py <url>

Requires:
    ANTHROPIC_API_KEY environment variable

The recipe schema is defined as a tool that Claude is forced to call,
which guarantees structured output matching the schema.
"""

import json
import os
import sys

import anthropic
from dotenv import load_dotenv
import requests

load_dotenv()

# ---------------------------------------------------------------------------
# Jina Reader
# ---------------------------------------------------------------------------

def fetch_via_jina(url: str) -> str:
    """Fetch webpage content as clean markdown via Jina Reader."""
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "Accept": "text/plain",
        "X-Return-Format": "markdown",
    }
    response = requests.get(jina_url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# Recipe schema (defined as an Anthropic tool)
# ---------------------------------------------------------------------------

EXTRACT_RECIPE_TOOL = {
    "name": "extract_recipe",
    "description": "Extract structured recipe information from webpage content.",
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
                            "description": "Optional preparation notes, e.g. 'finely chopped'.",
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
                "description": "Descriptive tags, e.g. ['vegetarian', 'gluten-free', 'quick'].",
                "items": {"type": "string"},
            },
        },
        "required": ["title", "ingredients", "steps"],
    },
}


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_recipe(url: str) -> dict:
    print(f"Fetching {url} via Jina Reader...", file=sys.stderr)
    content = fetch_via_jina(url)
    print(f"Fetched {len(content):,} characters", file=sys.stderr)

    client = anthropic.Anthropic()

    print("Calling Claude...", file=sys.stderr)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[EXTRACT_RECIPE_TOOL],
        # Force the model to call our tool rather than reply in prose
        tool_choice={"type": "tool", "name": "extract_recipe"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract the recipe from the following webpage content "
                    "and call the extract_recipe tool with the structured data.\n\n"
                    f"{content}"
                ),
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
        print("Usage: python extract_anthropic.py <url>", file=sys.stderr)
        sys.exit(1)

    result = extract_recipe(sys.argv[1])
    print(json.dumps(result, indent=2))
