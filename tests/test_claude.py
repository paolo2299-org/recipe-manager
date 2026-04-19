"""Tests for app.extraction.claude — Claude extraction orchestration."""

from unittest.mock import MagicMock, patch

import pytest

from app.extraction.claude import (
    ExtractionError,
    _call_claude,
    extract_from_image,
    extract_from_url,
)
from app.schemas.recipe import Recipe

from tests.conftest import SAMPLE_RECIPE


def _mock_claude_response(recipe_data):
    """Create a mock Anthropic API response with a tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "extract_recipe"
    tool_block.input = recipe_data

    response = MagicMock()
    response.content = [tool_block]
    response.usage.input_tokens = 100
    response.usage.output_tokens = 200
    return response


def _mock_claude_response_no_tool():
    """Create a mock response where the model didn't call the tool."""
    text_block = MagicMock()
    text_block.type = "text"

    response = MagicMock()
    response.content = [text_block]
    return response


class TestCallClaude:
    @patch("app.extraction.claude.anthropic.Anthropic")
    def test_successful_extraction(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_claude_response(SAMPLE_RECIPE)

        result = _call_claude([{"role": "user", "content": "test"}])

        assert result == SAMPLE_RECIPE

    @patch("app.extraction.claude.anthropic.Anthropic")
    def test_no_tool_call_raises(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_claude_response_no_tool()

        with pytest.raises(ExtractionError, match="did not call"):
            _call_claude([{"role": "user", "content": "test"}])


class TestExtractFromUrl:
    @patch("app.extraction.claude._call_claude")
    @patch("app.extraction.claude.fetch_via_jina")
    def test_success(self, mock_jina, mock_claude):
        mock_jina.return_value = "# Recipe Content"
        mock_claude.return_value = SAMPLE_RECIPE

        result = extract_from_url("https://example.com/recipe")

        assert result == Recipe.model_validate(SAMPLE_RECIPE)
        mock_jina.assert_called_once_with("https://example.com/recipe")
        mock_claude.assert_called_once()

    @patch("app.extraction.claude.fetch_via_jina")
    def test_jina_failure_raises_extraction_error(self, mock_jina):
        mock_jina.side_effect = ConnectionError("network error")

        with pytest.raises(ExtractionError, match="Failed to fetch URL"):
            extract_from_url("https://example.com/recipe")

    @patch("app.extraction.claude._call_claude")
    @patch("app.extraction.claude.fetch_via_jina")
    def test_claude_failure_raises_extraction_error(self, mock_jina, mock_claude):
        mock_jina.return_value = "content"
        mock_claude.side_effect = RuntimeError("API error")

        with pytest.raises(ExtractionError, match="Claude API call failed"):
            extract_from_url("https://example.com/recipe")


class TestExtractFromImage:
    @patch("app.extraction.claude._call_claude")
    @patch("app.extraction.claude.prepare_image")
    def test_success(self, mock_prepare, mock_claude):
        mock_prepare.return_value = ("base64data", "image/jpeg")
        mock_claude.return_value = SAMPLE_RECIPE

        result = extract_from_image(b"fake-image-bytes", "recipe.jpg")

        assert result == Recipe.model_validate(SAMPLE_RECIPE)
        mock_prepare.assert_called_once_with(b"fake-image-bytes", "recipe.jpg")
        mock_claude.assert_called_once()
        # Verify the image data was passed in the message
        msg = mock_claude.call_args[0][0][0]
        assert msg["content"][0]["source"]["data"] == "base64data"

    @patch("app.extraction.claude.prepare_image")
    def test_image_processing_failure(self, mock_prepare):
        mock_prepare.side_effect = ValueError("Unsupported format")

        with pytest.raises(ExtractionError, match="Image processing failed"):
            extract_from_image(b"fake", "recipe.bmp")

    @patch("app.extraction.claude._call_claude")
    @patch("app.extraction.claude.prepare_image")
    def test_claude_failure_raises_extraction_error(self, mock_prepare, mock_claude):
        mock_prepare.return_value = ("base64data", "image/jpeg")
        mock_claude.side_effect = RuntimeError("API error")

        with pytest.raises(ExtractionError, match="Claude API call failed"):
            extract_from_image(b"fake", "recipe.jpg")
