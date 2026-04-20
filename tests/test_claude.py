"""Tests for app.extraction.claude — Claude extraction orchestration."""

from unittest.mock import MagicMock, patch

import pytest

from app.extraction.claude import (
    ExtractionError,
    _call_claude,
    extract_from_image,
    extract_from_url,
    prefill_calories,
)
from app.schemas.calorie import MissingCalorie
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


class TestPrefillCalories:
    @patch("app.extraction.claude.anthropic.Anthropic")
    def test_success(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "fill_calories"
        tool_block.input = {
            "entries": [
                {"name": "flour", "unit": "g", "reference_quantity": 100, "calories": 364},
                {"name": "butter", "unit": "g", "reference_quantity": 100, "calories": 720},
            ]
        }
        response = MagicMock()
        response.content = [tool_block]
        response.usage.input_tokens = 50
        response.usage.output_tokens = 80
        mock_client.messages.create.return_value = response

        result = prefill_calories(
            [
                MissingCalorie(name="flour", unit="g"),
                MissingCalorie(name="butter", unit="g"),
            ]
        )

        assert len(result) == 2
        assert result[0].name == "flour"
        assert result[0].reference_quantity == 100
        assert result[0].calories == 364
        assert result[1].name == "butter"
        assert result[1].calories == 720

    def test_empty_input_returns_empty_without_calling_claude(self):
        with patch("app.extraction.claude.anthropic.Anthropic") as mock_cls:
            assert prefill_calories([]) == []
            mock_cls.assert_not_called()

    @patch("app.extraction.claude.anthropic.Anthropic")
    def test_api_failure_raises_extraction_error(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = RuntimeError("boom")

        with pytest.raises(ExtractionError, match="Claude API call failed"):
            prefill_calories([MissingCalorie(name="flour", unit="g")])

    @patch("app.extraction.claude.anthropic.Anthropic")
    def test_invalid_payload_raises_extraction_error(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "fill_calories"
        # reference_quantity must be > 0 per CalorieEntry validation.
        tool_block.input = {
            "entries": [
                {"name": "flour", "unit": "g", "reference_quantity": 0, "calories": 0}
            ]
        }
        response = MagicMock()
        response.content = [tool_block]
        response.usage.input_tokens = 1
        response.usage.output_tokens = 1
        mock_client.messages.create.return_value = response

        with pytest.raises(ExtractionError, match="invalid calorie suggestions"):
            prefill_calories([MissingCalorie(name="flour", unit="g")])
