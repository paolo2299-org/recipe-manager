"""Recipe routes blueprint."""

import json
import logging

from flask import (
    Blueprint,
    Response,
    abort,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from pydantic import ValidationError
from werkzeug.wrappers import Response as WerkzeugResponse

from app.extraction.claude import (
    ExtractionError,
    edit_recipe,
    extract_from_image,
    extract_from_url,
)
from app.schemas.forms import (
    CalorieBatchForm,
    EditInstructionForm,
    ExtractUrlForm,
    IdeaForm,
    first_error_msg,
)
from app.schemas.recipe import ALLOWED_RECIPE_TAGS, Recipe
from app.storage.calories import list_missing_for_recipe, upsert_calorie
from app.storage.recipes import (
    RECORD_TYPE_IDEA,
    delete_recipe,
    get_recipe,
    list_recipes,
    save_recipe,
    update_recipe,
)

logger = logging.getLogger(__name__)

bp = Blueprint("recipes", __name__)


def _get_idea_or_404(recipe_id: str) -> Recipe:
    recipe = get_recipe(recipe_id)
    if recipe is None or recipe.record_type != RECORD_TYPE_IDEA:
        abort(404)
    return recipe


@bp.route("/")
def index() -> str:
    try:
        recipes = list_recipes()
        load_error: str | None = None
    except Exception as e:
        logger.exception("Failed to load recipes")
        recipes = []
        load_error = str(e)

    return render_template("index.html", recipes=recipes, load_error=load_error)


@bp.route("/recipes/<recipe_id>")
def detail(recipe_id: str) -> str:
    recipe = get_recipe(recipe_id)
    if recipe is None:
        abort(404)
    return render_template("detail.html", recipe=recipe)


@bp.route("/recipes/<recipe_id>/edit")
def edit_idea(recipe_id: str) -> str:
    recipe = _get_idea_or_404(recipe_id)
    return render_template(
        "edit_idea.html",
        recipe=recipe,
        allowed_recipe_tags=ALLOWED_RECIPE_TAGS,
        selected_idea_tags=recipe.tags,
        error=None,
    )


@bp.route("/recipes/<recipe_id>/edit", methods=["POST"])
def update_idea(recipe_id: str) -> Response | WerkzeugResponse | str:
    recipe = _get_idea_or_404(recipe_id)
    submitted_title = request.form.get("title", "")
    submitted_description = request.form.get("description", "")
    selected_idea_tags: list[str] = []
    try:
        form = IdeaForm.from_form(request.form)
        selected_idea_tags = form.tags
        updated = recipe.model_copy(
            update={
                "title": form.title,
                "description": form.description,
                "tags": form.tags,
            }
        )
        update_recipe(recipe_id, updated)
        return redirect(url_for("recipes.detail", recipe_id=recipe_id))
    except ValidationError as e:
        logger.info("Idea update failed validation")
        return render_template(
            "edit_idea.html",
            recipe=recipe.model_copy(
                update={"title": submitted_title, "description": submitted_description}
            ),
            allowed_recipe_tags=ALLOWED_RECIPE_TAGS,
            selected_idea_tags=selected_idea_tags,
            error=first_error_msg(e),
        )
    except Exception as e:
        logger.exception("Idea update failed")
        return render_template(
            "edit_idea.html",
            recipe=recipe.model_copy(
                update={"title": submitted_title, "description": submitted_description}
            ),
            allowed_recipe_tags=ALLOWED_RECIPE_TAGS,
            selected_idea_tags=selected_idea_tags,
            error=str(e),
        )


@bp.route("/recipes/<recipe_id>/calories/edit")
def edit_calories(recipe_id: str) -> Response | WerkzeugResponse | str:
    recipe = get_recipe(recipe_id)
    if recipe is None or recipe.record_type == RECORD_TYPE_IDEA:
        abort(404)
    missing = list_missing_for_recipe(recipe)
    if not missing:
        return redirect(url_for("recipes.detail", recipe_id=recipe_id))
    return render_template(
        "edit_calories.html",
        recipe=recipe,
        missing=missing,
        error=None,
    )


@bp.route("/recipes/<recipe_id>/calories/edit", methods=["POST"])
def save_calories(recipe_id: str) -> Response | WerkzeugResponse | str:
    recipe = get_recipe(recipe_id)
    if recipe is None or recipe.record_type == RECORD_TYPE_IDEA:
        abort(404)

    try:
        batch = CalorieBatchForm.from_form(request.form)
        for entry in batch.entries:
            upsert_calorie(
                entry["name"],
                entry["unit"],
                float(entry["reference_quantity"]),
                float(entry["calories"]),
            )
        update_recipe(recipe_id, recipe)
        return redirect(url_for("recipes.detail", recipe_id=recipe_id))
    except ValidationError as e:
        logger.info("Saving calorie info failed validation")
        missing = list_missing_for_recipe(recipe)
        return render_template(
            "edit_calories.html",
            recipe=recipe,
            missing=missing,
            error=first_error_msg(e),
        )
    except Exception as e:
        logger.exception("Saving calorie info failed")
        missing = list_missing_for_recipe(recipe)
        return render_template(
            "edit_calories.html",
            recipe=recipe,
            missing=missing,
            error=str(e),
        )


@bp.route("/recipes/add")
def add() -> str:
    return render_template(
        "add.html",
        allowed_recipe_tags=ALLOWED_RECIPE_TAGS,
        selected_idea_tags=[],
    )


@bp.route("/recipes/extract/url", methods=["POST"])
def extract_url() -> str:
    try:
        form = ExtractUrlForm.model_validate({"url": request.form.get("url", "")})
    except ValidationError as e:
        return render_template("partials/extraction_error.html", error=first_error_msg(e))

    try:
        recipe = extract_from_url(form.url)
        return render_template(
            "partials/extraction_result.html",
            recipe=recipe,
            recipe_json=recipe.model_dump_json(),
            source_type="url",
            source_ref=form.url,
        )
    except ExtractionError as e:
        logger.exception("URL extraction failed")
        return render_template("partials/extraction_error.html", error=str(e))


@bp.route("/recipes/extract/image", methods=["POST"])
def extract_image() -> str:
    file = request.files.get("image")
    if not file or not file.filename:
        return render_template("partials/extraction_error.html", error="Image is required")
    filename = file.filename
    try:
        file_bytes = file.read()
        recipe = extract_from_image(file_bytes, filename)
        return render_template(
            "partials/extraction_result.html",
            recipe=recipe,
            recipe_json=recipe.model_dump_json(),
            source_type="image",
            source_ref=file.filename,
        )
    except ExtractionError as e:
        logger.exception("Image extraction failed")
        return render_template("partials/extraction_error.html", error=str(e))


@bp.route("/recipes/save", methods=["POST"])
def save() -> Response | str:
    recipe_json = request.form.get("recipe_json")
    source_type = request.form.get("source_type", "")
    source_ref = request.form.get("source_ref", "")
    if not recipe_json:
        return render_template("partials/extraction_error.html", error="No recipe data")
    try:
        recipe = Recipe.model_validate(json.loads(recipe_json))
        recipe_id = save_recipe(recipe, source_type, source_ref)
        response = make_response()
        response.headers["HX-Redirect"] = url_for("recipes.detail", recipe_id=recipe_id)
        return response
    except ValidationError as e:
        logger.info("Save failed validation")
        return render_template("partials/extraction_error.html", error=first_error_msg(e))
    except Exception as e:
        logger.exception("Save failed")
        return render_template("partials/extraction_error.html", error=str(e))


@bp.route("/recipes/create-idea", methods=["POST"])
def create_idea() -> Response | str:
    try:
        form = IdeaForm.from_form(request.form)
        idea = Recipe(
            record_type=RECORD_TYPE_IDEA,
            title=form.title,
            description=form.description or None,
            ingredients=[],
            steps=[],
            tags=form.tags,
        )
        recipe_id = save_recipe(idea, "manual", "")
        response = make_response()
        response.headers["HX-Redirect"] = url_for("recipes.detail", recipe_id=recipe_id)
        return response
    except ValidationError as e:
        logger.info("Idea save failed validation")
        return render_template("partials/entry_error.html", error=first_error_msg(e))
    except Exception as e:
        logger.exception("Idea save failed")
        return render_template("partials/entry_error.html", error=str(e))


@bp.route("/recipes/<recipe_id>/edit-preview", methods=["POST"])
def edit_preview(recipe_id: str) -> str:
    recipe = get_recipe(recipe_id)
    if recipe is None:
        abort(404)
    if recipe.record_type == RECORD_TYPE_IDEA:
        abort(404)

    try:
        instruction_form = EditInstructionForm.model_validate(
            {"instruction": request.form.get("instruction", "")}
        )
    except ValidationError as e:
        return render_template(
            "partials/recipe_edit_error.html",
            error=first_error_msg(e),
        )

    try:
        edited = edit_recipe(recipe, instruction_form.instruction)
        edited_recipe = Recipe.model_validate(
            {**edited.recipe.model_dump(), "record_type": recipe.record_type}
        )
        return render_template(
            "partials/recipe_edit_preview.html",
            recipe=edited_recipe,
            recipe_id=recipe_id,
            recipe_json=edited_recipe.model_dump_json(),
            change_summary=edited.change_summary,
            warnings=edited.warnings,
        )
    except ExtractionError as e:
        logger.exception("Recipe edit preview failed")
        return render_template("partials/recipe_edit_error.html", error=str(e))
    except Exception as e:
        logger.exception("Recipe edit preview failed")
        return render_template("partials/recipe_edit_error.html", error=str(e))


@bp.route("/recipes/<recipe_id>/apply-edit", methods=["POST"])
def apply_edit(recipe_id: str) -> Response | str:
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
        edited = Recipe.model_validate(json.loads(recipe_json))
        update_recipe(recipe_id, edited)
        response = make_response()
        response.headers["HX-Redirect"] = url_for("recipes.detail", recipe_id=recipe_id)
        return response
    except ValidationError as e:
        logger.info("Apply edit failed validation")
        return render_template("partials/recipe_edit_error.html", error=first_error_msg(e))
    except Exception as e:
        logger.exception("Apply edit failed")
        return render_template("partials/recipe_edit_error.html", error=str(e))


@bp.route("/recipes/<recipe_id>/delete", methods=["POST"])
def delete(recipe_id: str) -> Response:
    delete_recipe(recipe_id)
    response = make_response()
    response.headers["HX-Redirect"] = url_for("recipes.index")
    return response
