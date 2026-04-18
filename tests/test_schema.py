"""Tests for extraction tool schema constraints."""

from app.extraction.schema import ALLOWED_RECIPE_TAGS, EXTRACT_RECIPE_TOOL


def test_tags_are_restricted_to_allowed_cuisine_keywords():
    tags_schema = EXTRACT_RECIPE_TOOL["input_schema"]["properties"]["tags"]

    assert tags_schema["items"]["enum"] == ALLOWED_RECIPE_TAGS
    assert "Cuisine tags only" in tags_schema["description"]
