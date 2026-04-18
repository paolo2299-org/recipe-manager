"""Recipe routes blueprint."""

import json
import logging

from flask import Blueprint, abort, make_response, render_template, request, url_for

from app.extraction.claude import (
    ExtractionError,
    edit_recipe,
    extract_from_image,
    extract_from_url,
)
from app.storage.recipes import (
    delete_recipe,
    get_recipe,
    list_recipes,
    normalize_recipe_data,
    save_recipe,
    update_recipe,
)

logger = logging.getLogger(__name__)

bp = Blueprint("recipes", __name__)


@bp.route("/")
def index():
    try:
        recipes = list_recipes()
        load_error = None
    except Exception as e:
        logger.exception("Failed to load recipes")
        recipes = []
        load_error = str(e)

    return render_template("index.html", recipes=recipes, load_error=load_error)


@bp.route("/recipes/<recipe_id>")
def detail(recipe_id):
    recipe = get_recipe(recipe_id)
    if recipe is None:
        abort(404)
    return render_template("detail.html", recipe=recipe)


@bp.route("/recipes/add")
def add():
    return render_template("add.html")


@bp.route("/recipes/extract/url", methods=["POST"])
def extract_url():
    url = request.form.get("url", "").strip()
    if not url:
        return render_template("partials/extraction_error.html", error="URL is required")
    try:
        recipe_data = extract_from_url(url)
        recipe_json = json.dumps(recipe_data)
        return render_template(
            "partials/extraction_result.html",
            recipe=recipe_data,
            recipe_json=recipe_json,
            source_type="url",
            source_ref=url,
        )
    except ExtractionError as e:
        logger.exception("URL extraction failed")
        return render_template("partials/extraction_error.html", error=str(e))


@bp.route("/recipes/extract/image", methods=["POST"])
def extract_image():
    file = request.files.get("image")
    if not file or file.filename == "":
        return render_template("partials/extraction_error.html", error="Image is required")
    try:
        file_bytes = file.read()
        recipe_data = extract_from_image(file_bytes, file.filename)
        recipe_json = json.dumps(recipe_data)
        return render_template(
            "partials/extraction_result.html",
            recipe=recipe_data,
            recipe_json=recipe_json,
            source_type="image",
            source_ref=file.filename,
        )
    except ExtractionError as e:
        logger.exception("Image extraction failed")
        return render_template("partials/extraction_error.html", error=str(e))


@bp.route("/recipes/save", methods=["POST"])
def save():
    recipe_json = request.form.get("recipe_json")
    source_type = request.form.get("source_type", "")
    source_ref = request.form.get("source_ref", "")
    if not recipe_json:
        return render_template("partials/extraction_error.html", error="No recipe data")
    try:
        recipe_data = json.loads(recipe_json)
        recipe_id = save_recipe(recipe_data, source_type, source_ref)
        response = make_response()
        response.headers["HX-Redirect"] = url_for("recipes.detail", recipe_id=recipe_id)
        return response
    except Exception as e:
        logger.exception("Save failed")
        return render_template("partials/extraction_error.html", error=str(e))


@bp.route("/recipes/<recipe_id>/edit-preview", methods=["POST"])
def edit_preview(recipe_id):
    recipe = get_recipe(recipe_id)
    if recipe is None:
        abort(404)

    instruction = request.form.get("instruction", "").strip()
    if not instruction:
        return render_template(
            "partials/recipe_edit_error.html",
            error="Edit instruction is required",
        )

    try:
        result = edit_recipe(recipe, instruction)
        edited_recipe = normalize_recipe_data(result["recipe"])
        change_summary = result.get("change_summary", "")
        warnings = result.get("warnings", [])
        if not isinstance(change_summary, str):
            raise ValueError("Change summary must be a string")
        if not isinstance(warnings, list):
            raise ValueError("Warnings must be a list")
        recipe_json = json.dumps(edited_recipe)
        return render_template(
            "partials/recipe_edit_preview.html",
            recipe=edited_recipe,
            recipe_id=recipe_id,
            recipe_json=recipe_json,
            change_summary=change_summary,
            warnings=warnings,
        )
    except ExtractionError as e:
        logger.exception("Recipe edit preview failed")
        return render_template("partials/recipe_edit_error.html", error=str(e))
    except Exception as e:
        logger.exception("Recipe edit preview failed")
        return render_template("partials/recipe_edit_error.html", error=str(e))


@bp.route("/recipes/<recipe_id>/apply-edit", methods=["POST"])
def apply_edit(recipe_id):
    recipe = get_recipe(recipe_id)
    if recipe is None:
        abort(404)

    recipe_json = request.form.get("recipe_json")
    if not recipe_json:
        return render_template(
            "partials/recipe_edit_error.html",
            error="No edited recipe data",
        )

    try:
        recipe_data = json.loads(recipe_json)
        update_recipe(recipe_id, recipe_data)
        response = make_response()
        response.headers["HX-Redirect"] = url_for("recipes.detail", recipe_id=recipe_id)
        return response
    except Exception as e:
        logger.exception("Apply edit failed")
        return render_template("partials/recipe_edit_error.html", error=str(e))


@bp.route("/recipes/<recipe_id>/delete", methods=["POST"])
def delete(recipe_id):
    delete_recipe(recipe_id)
    response = make_response()
    response.headers["HX-Redirect"] = url_for("recipes.index")
    return response
