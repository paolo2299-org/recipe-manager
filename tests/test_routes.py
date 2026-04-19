"""Tests for Flask routes."""

import io
import json
from unittest.mock import patch

from app.schemas.recipe import EditedRecipe, Recipe
from tests.conftest import SAMPLE_RECIPE, make_recipe


def _sample_recipe_model() -> Recipe:
    return Recipe.model_validate(SAMPLE_RECIPE)


def _idea_model(**overrides) -> Recipe:
    base = {
        "id": "idea-1",
        "record_type": "idea",
        "title": "Chicken shawarma bowls",
        "description": "Try with pickled onions.",
        "servings": None,
        "prep_time": None,
        "cook_time": None,
        "total_time": None,
        "ingredients": [],
        "steps": [],
        "tags": ["British", "Thai"],
        "source_type": "manual",
        "source_ref": "",
    }
    base.update(overrides)
    return Recipe.model_validate(base)


class TestIndex:
    @patch("app.routes.recipes.list_recipes")
    def test_index_renders(self, mock_list, client):
        mock_list.return_value = [make_recipe()]

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
        mock_get.return_value = make_recipe()

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

    @patch("app.routes.recipes.get_recipe")
    def test_detail_for_idea_shows_placeholders(self, mock_get, client):
        mock_get.return_value = _idea_model(tags=["dinner"])

        response = client.get("/recipes/idea-1")

        assert response.status_code == 200
        assert b"Recipe idea" in response.data
        assert b'href="/recipes/idea-1/edit"' in response.data
        assert b"No ingredients saved yet." in response.data
        assert b"No steps saved yet." in response.data
        assert b"Generating edited recipe preview with AI" not in response.data


class TestAdd:
    def test_add_hub_renders(self, client):
        response = client.get("/recipes/add")

        assert response.status_code == 200
        assert b'href="/recipes/add/from-link"' in response.data
        assert b'href="/recipes/add/from-photo"' in response.data
        assert b'href="/recipes/add/idea"' in response.data

    def test_add_from_link_page_renders(self, client):
        response = client.get("/recipes/add/from-link")

        assert response.status_code == 200
        assert b'hx-post="/recipes/extract/url"' in response.data
        assert b'name="url"' in response.data

    def test_add_from_photo_page_renders(self, client):
        response = client.get("/recipes/add/from-photo")

        assert response.status_code == 200
        assert b'hx-post="/recipes/extract/image"' in response.data
        assert b'name="image"' in response.data

    def test_add_idea_page_renders(self, client):
        response = client.get("/recipes/add/idea")

        assert response.status_code == 200
        assert b'hx-post="/recipes/create-idea"' in response.data
        assert b"Cuisine Tags" in response.data
        assert b"British" in response.data


class TestExtractUrl:
    @patch("app.routes.recipes.extract_from_url")
    def test_success(self, mock_extract, client):
        mock_extract.return_value = _sample_recipe_model()

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
        mock_extract.return_value = _sample_recipe_model()

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
        mock_save.assert_called_once_with(
            _sample_recipe_model(), "url", "https://example.com"
        )

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


class TestCreateIdea:
    @patch("app.routes.recipes.save_recipe")
    def test_success_redirects(self, mock_save, client):
        mock_save.return_value = "idea-id"

        response = client.post(
            "/recipes/create-idea",
            data={
                "title": "Gochujang noodles",
                "tags": ["British", "Thai"],
                "description": "Try with sesame cucumbers.",
            },
        )

        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/recipes/idea-id"
        expected = Recipe(
            record_type="idea",
            title="Gochujang noodles",
            description="Try with sesame cucumbers.",
            ingredients=[],
            steps=[],
            tags=["British", "Thai"],
        )
        mock_save.assert_called_once_with(expected, "manual", "")

    def test_missing_title_shows_error(self, client):
        response = client.post(
            "/recipes/create-idea",
            data={"title": "", "tags": ["British"]},
        )

        assert response.status_code == 200
        assert b"Could not save entry" in response.data
        assert b"Title is required" in response.data

    def test_invalid_tag_shows_error(self, client):
        response = client.post(
            "/recipes/create-idea",
            data={"title": "Gochujang noodles", "tags": ["Not-A-Real-Tag"]},
        )

        assert response.status_code == 200
        assert b"Could not save entry" in response.data
        assert b"Invalid cuisine tag" in response.data


class TestEditIdea:
    @patch("app.routes.recipes.get_recipe")
    def test_edit_page_renders_for_idea(self, mock_get, client):
        mock_get.return_value = _idea_model(tags=["British", "Thai"])

        response = client.get("/recipes/idea-1/edit")

        assert response.status_code == 200
        assert b"Edit Recipe Idea" in response.data
        assert b"Chicken shawarma bowls" in response.data
        assert b"British" in response.data
        assert b"Thai" in response.data

    @patch("app.routes.recipes.get_recipe")
    def test_edit_page_404_for_non_idea(self, mock_get, client):
        mock_get.return_value = make_recipe()

        response = client.get("/recipes/abc123/edit")

        assert response.status_code == 404

    @patch("app.routes.recipes.update_recipe")
    @patch("app.routes.recipes.get_recipe")
    def test_update_redirects_to_detail(self, mock_get, mock_update, client):
        initial = _idea_model(tags=["British"])
        mock_get.return_value = initial

        response = client.post(
            "/recipes/idea-1/edit",
            data={
                "title": "Crispy chicken shawarma bowls",
                "tags": ["British", "Thai"],
                "description": "Add garlicky yogurt.",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/recipes/idea-1"
        expected = initial.model_copy(
            update={
                "title": "Crispy chicken shawarma bowls",
                "description": "Add garlicky yogurt.",
                "tags": ["British", "Thai"],
            }
        )
        mock_update.assert_called_once_with("idea-1", expected)

    @patch("app.routes.recipes.update_recipe")
    @patch("app.routes.recipes.get_recipe")
    def test_update_re_renders_on_error(self, mock_get, mock_update, client):
        mock_get.return_value = _idea_model(description=None, tags=["British"])
        mock_update.side_effect = ValueError("Title is required")

        response = client.post(
            "/recipes/idea-1/edit",
            data={"title": "", "tags": ["British"], "description": ""},
        )

        assert response.status_code == 200
        assert b"Could not save idea" in response.data
        assert b"Title is required" in response.data


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
        mock_get.return_value = make_recipe()
        mock_edit.return_value = EditedRecipe.model_validate(
            {
                "recipe": {**SAMPLE_RECIPE, "title": "Peruvian Pancakes"},
                "change_summary": "Changed the recipe title.",
                "warnings": ["Servings were left unchanged."],
            }
        )

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
        mock_get.return_value = make_recipe()

        response = client.post("/recipes/abc123/edit-preview", data={"instruction": ""})

        assert response.status_code == 200
        assert b"Edit instruction is required" in response.data

    @patch("app.routes.recipes.edit_recipe")
    @patch("app.routes.recipes.get_recipe")
    def test_model_error(self, mock_get, mock_edit, client):
        from app.extraction.claude import ExtractionError

        mock_get.return_value = make_recipe()
        mock_edit.side_effect = ExtractionError("Could not update recipe")

        response = client.post(
            "/recipes/abc123/edit-preview",
            data={"instruction": "double the tomatoes"},
        )

        assert response.status_code == 200
        assert b"Could not update recipe" in response.data

    @patch("app.routes.recipes.get_recipe")
    def test_ideas_cannot_use_ai_edit_preview(self, mock_get, client):
        mock_get.return_value = _idea_model(tags=["dinner"])

        response = client.post(
            "/recipes/idea-1/edit-preview",
            data={"instruction": "add chicken"},
        )

        assert response.status_code == 404


class TestApplyEdit:
    @patch("app.routes.recipes.update_recipe")
    @patch("app.routes.recipes.get_recipe")
    def test_success_redirects(self, mock_get, mock_update, client):
        mock_get.return_value = make_recipe()

        response = client.post(
            "/recipes/abc123/apply-edit",
            data={"recipe_json": json.dumps(SAMPLE_RECIPE)},
        )

        assert response.status_code == 200
        assert response.headers["HX-Redirect"] == "/recipes/abc123"
        mock_update.assert_called_once_with("abc123", _sample_recipe_model())

    @patch("app.routes.recipes.get_recipe")
    def test_missing_recipe_json(self, mock_get, client):
        mock_get.return_value = make_recipe()

        response = client.post("/recipes/abc123/apply-edit", data={})

        assert response.status_code == 200
        assert b"No edited recipe data" in response.data
