"""Tests for app.extraction.jina — Jina Reader URL fetching."""

from unittest.mock import patch, MagicMock

import pytest
import requests

from app.extraction.jina import fetch_via_jina


class TestFetchViaJina:
    @patch("app.extraction.jina.requests.get")
    def test_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "# Recipe Title\nSome content"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_via_jina("https://example.com/recipe")

        assert result == "# Recipe Title\nSome content"
        mock_get.assert_called_once_with(
            "https://r.jina.ai/https://example.com/recipe",
            headers={"Accept": "text/plain", "X-Return-Format": "markdown"},
            timeout=30,
        )
        mock_response.raise_for_status.assert_called_once()

    @patch("app.extraction.jina.requests.get")
    def test_http_error_propagates(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404")
        mock_get.return_value = mock_response

        with pytest.raises(requests.HTTPError):
            fetch_via_jina("https://example.com/bad")
