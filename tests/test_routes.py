"""Tests for Flask routes."""

import io
import json
from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import SAMPLE_RECIPE, SAMPLE_RECIPE_DB


class TestIndex:
    @patch("app.routes.recipes.list_recipes")
    def test_index_renders(self, mock_list, client):
        mock_list.return_value = [SAMPLE_RECIPE_DB]

        response = client.get("/")

        assert response.status_code == 200
        assert b"Test Cookies" in response.data

    @patch("app.routes.recipes.list_recipes")
    def test_index_empty(self, mock_list, client):
        mock_list.return_value = []

        response = client.get("/")

        assert response.status_code == 200
        assert b"No recipes yet" in response.data

    @patch("app.routes.recipes.list_recipes")
    def test_index_shows_database_error(self, mock_list, client):
        mock_list.side_effect = RuntimeError("Database is misconfigured")

        response = client.get("/")

        assert response.status_code == 200
        assert b"Database error" in response.data
        assert b"Database is misconfigured" in response.data


class TestDetail:
    @patch("app.routes.recipes.get_recipe")
    def test_detail_found(self, mock_get, client):
        mock_get.return_value = SAMPLE_RECIPE_DB

        response = client.get("/recipes/abc123")

        assert response.status_code == 200
        assert b"Test Cookies" in response.data
        assert b"Mix dry ingredients" in response.data
        assert b"Generating edited recipe preview with AI" in response.data

    @patch("app.routes.recipes.get_recipe")
    def test_detail_not_found(self, mock_get, client):
        mock_get.return_value = None

        response = client.get("/recipes/nonexistent")

        assert response.status_code == 404


class TestAdd:
    def test_add_page_renders(self, client):
        response = client.get("/recipes/add")

        assert response.status_code == 200
        assert b"From URL" in response.data
        assert b"From Image" in response.data


class TestExtractUrl:
    @patch("app.routes.recipes.extract_from_url")
    def test_success(self, mock_extract, client):
        mock_extract.return_value = SAMPLE_RECIPE

        response = client.post(
            "/recipes/extract/url",
            data={"url": "https://example.com/recipe"},
        )

        assert response.status_code == 200
        assert b"Test Cookies" in response.data
        assert b"Save to Collection" in response.data

    def test_missing_url(self, client):
        response = client.post("/recipes/extract/url", data={"url": ""})

        assert response.status_code == 200
        assert b"URL is required" in response.data

    @patch("app.routes.recipes.extract_from_url")
    def test_extraction_error(self, mock_extract, client):
        from app.extraction.claude import ExtractionError

        mock_extract.side_effect = ExtractionError("Could not parse recipe")

        response = client.post(
            "/recipes/extract/url",
            data={"url": "https://example.com/bad"},
        )

        assert response.status_code == 200
        assert b"Could not parse recipe" in response.data


class TestExtractImage:
    @patch("app.routes.recipes.extract_from_image")
    def test_success(self, mock_extract, client):
        mock_extract.return_value = SAMPLE_RECIPE

        response = client.post(
            "/recipes/extract/image",
            data={"image": (io.BytesIO(b"fake-image"), "recipe.jpg")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        assert b"Test Cookies" in response.data
        assert b"Save to Collection" in response.data

    def test_missing_image(self, client):
        response = client.post("/recipes/extract/image", data={})

        assert response.status_code == 200
        assert b"Image is required" in response.data

    @patch("app.routes.recipes.extract_from_image")
    def test_extraction_error(self, mock_extract, client):
        from app.extraction.claude import ExtractionError

        mock_extract.side_effect = ExtractionError("Bad image")

        response = client.post(
            "/recipes/extract/image",
            data={"image": (io.BytesIO(b"fake"), "bad.jpg")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        assert b"Bad image" in response.data


class TestSave:
    @patch("app.routes.recipes.save_recipe")
    def test_success_redirects(self, mock_save, client):
        mock_save.return_value = "new-id"
        recipe_json = json.dumps(SAMPLE_RECIPE)

        response = client.post(
            "/recipes/save",
            data={
                "recipe_json": recipe_json,
                "source_type": "url",
                "source_ref": "https://example.com",
            },
        )

        assert response.status_code == 200
        assert "HX-Redirect" in response.headers
        assert "/recipes/new-id" in response.headers["HX-Redirect"]

    def test_missing_recipe_json(self, client):
        response = client.post("/recipes/save", data={})

        assert response.status_code == 200
        assert b"No recipe data" in response.data

    @patch("app.routes.recipes.save_recipe")
    def test_save_error(self, mock_save, client):
        mock_save.side_effect = Exception("Database down")

        response = client.post(
            "/recipes/save",
            data={
                "recipe_json": json.dumps(SAMPLE_RECIPE),
                "source_type": "url",
                "source_ref": "https://example.com",
            },
        )

        assert response.status_code == 200
        assert b"Database down" in response.data


class TestDelete:
    @patch("app.routes.recipes.delete_recipe")
    def test_delete_redirects(self, mock_delete, client):
        response = client.post("/recipes/abc123/delete")

        assert response.status_code == 200
        assert "HX-Redirect" in response.headers
        assert response.headers["HX-Redirect"] == "/"
        mock_delete.assert_called_once_with("abc123")


class TestEditPreview:
    @patch("app.routes.recipes.edit_recipe")
    @patch("app.routes.recipes.get_recipe")
    def test_success(self, mock_get, mock_edit, client):
        mock_get.return_value = SAMPLE_RECIPE_DB
        mock_edit.return_value = {
            "recipe": {**SAMPLE_RECIPE, "title": "Peruvian Pancakes"},
            "change_summary": "Changed the recipe title.",
            "warnings": ["Servings were left unchanged."],
        }

        response = client.post(
            "/recipes/abc123/edit-preview",
            data={"instruction": "change the title to Peruvian Pancakes"},
        )

        assert response.status_code == 200
        assert b"Edited Recipe Preview" in response.data
        assert b"Peruvian Pancakes" in response.data
        assert b"Changed the recipe title." in response.data
        assert b"Apply Changes" in response.data

    @patch("app.routes.recipes.get_recipe")
    def test_missing_instruction(self, mock_get, client):
        mock_get.return_value = SAMPLE_RECIPE_DB

        response = client.post("/recipes/abc123/edit-preview", data={"instruction": ""})

        assert response.status_code == 200
        assert b"Edit instruction is required" in response.data

    @patch("app.routes.recipes.edit_recipe")
    @patch("app.routes.recipes.get_recipe")
    def test_model_error(self, mock_get, mock_edit, client):
        from app.extraction.claude import ExtractionError

        mock_get.return_value = SAMPLE_RECIPE_DB
        mock_edit.side_effect = ExtractionError("Could not update recipe")

        response = client.post(
            "/recipes/abc123/edit-preview",
            data={"instruction": "double the tomatoes"},
        )

        assert response.status_code == 200
        assert b"Could not update recipe" in response.data


class TestApplyEdit:
    @patch("app.routes.recipes.update_recipe")
    @patch("app.routes.recipes.get_recipe")
    def test_success_redirects(self, mock_get, mock_update, client):
        mock_get.return_value = SAMPLE_RECIPE_DB

        response = client.post(
            "/recipes/abc123/apply-edit",
            data={"recipe_json": json.dumps(SAMPLE_RECIPE)},
        )

        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/recipes/abc123"
        mock_update.assert_called_once_with("abc123", SAMPLE_RECIPE)

    @patch("app.routes.recipes.get_recipe")
    def test_missing_recipe_json(self, mock_get, client):
        mock_get.return_value = SAMPLE_RECIPE_DB

        response = client.post("/recipes/abc123/apply-edit", data={})

        assert response.status_code == 200
        assert b"No edited recipe data" in response.data
