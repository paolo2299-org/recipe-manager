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

from app.calories.breakdown import build_breakdown
from app.extraction.claude import (
    ExtractionError,
    edit_recipe,
    extract_from_image,
    extract_from_url,
    prefill_calories,
)
from app.schemas.forms import (
    CalorieBatchForm,
    EditInstructionForm,
    ExtractUrlForm,
    IdeaForm,
    IngredientQuantityForm,
    first_error_msg,
)
from app.schemas.recipe import ALLOWED_RECIPE_TAGS, Recipe
from app.storage.calories import (
    get_calorie,
    list_missing_for_recipe,
    list_unparseable_for_recipe,
    servings_needs_fix,
    upsert_calorie,
)
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


@bp.route("/recipes/<recipe_id>/calories/breakdown")
def breakdown(recipe_id: str) -> Response | WerkzeugResponse | str:
    recipe = get_recipe(recipe_id)
    if recipe is None or recipe.record_type == RECORD_TYPE_IDEA:
        abort(404)
    if recipe.calories_per_serving is None:
        return redirect(url_for("recipes.edit_calories", recipe_id=recipe_id))
    rows = build_breakdown(recipe)
    return render_template("breakdown.html", recipe=recipe, rows=rows)


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


def _single_ingredient_item(
    name: str, unit: str | None
) -> dict[str, object]:
    """Build the edit-form item dict for a single ingredient, pre-filled if a row exists."""
    entry = get_calorie(name, unit)
    return {
        "name": name,
        "unit": unit or None,
        "reference_quantity": entry.reference_quantity if entry is not None else None,
        "calories": entry.calories if entry is not None else None,
    }


@bp.route("/recipes/<recipe_id>/calories/edit")
def edit_calories(recipe_id: str) -> Response | WerkzeugResponse | str:
    recipe = get_recipe(recipe_id)
    if recipe is None or recipe.record_type == RECORD_TYPE_IDEA:
        abort(404)
    scope_name = request.args.get("name", "").strip()
    scope_unit = request.args.get("unit", "").strip() or None
    return_to = request.args.get("return_to", "").strip()
    single_mode = bool(scope_name)

    if servings_needs_fix(recipe) or list_unparseable_for_recipe(recipe):
        return redirect(
            url_for("recipes.edit_ingredient_quantities", recipe_id=recipe_id)
        )

    if single_mode:
        items: list[dict[str, object]] = [
            _single_ingredient_item(scope_name, scope_unit)
        ]
    else:
        missing = list_missing_for_recipe(recipe)
        if not missing:
            return redirect(url_for("recipes.detail", recipe_id=recipe_id))
        items = [
            {"name": item.name, "unit": item.unit, "reference_quantity": None, "calories": None}
            for item in missing
        ]

    return render_template(
        "edit_calories.html",
        recipe=recipe,
        items=items,
        single_mode=single_mode,
        return_to=return_to,
        error=None,
    )


def _missing_items(recipe: Recipe) -> list[dict[str, object]]:
    return [
        {"name": item.name, "unit": item.unit, "reference_quantity": None, "calories": None}
        for item in list_missing_for_recipe(recipe)
    ]


@bp.route("/recipes/<recipe_id>/calories/prefill", methods=["POST"])
def prefill_calories_route(recipe_id: str) -> Response | WerkzeugResponse | str:
    recipe = get_recipe(recipe_id)
    if recipe is None or recipe.record_type == RECORD_TYPE_IDEA:
        abort(404)
    if servings_needs_fix(recipe) or list_unparseable_for_recipe(recipe):
        return redirect(
            url_for("recipes.edit_ingredient_quantities", recipe_id=recipe_id)
        )
    missing = list_missing_for_recipe(recipe)
    if not missing:
        return redirect(url_for("recipes.detail", recipe_id=recipe_id))

    try:
        entries = prefill_calories(missing)
        items = [
            {
                "name": item.name,
                "unit": item.unit,
                "reference_quantity": entry.reference_quantity,
                "calories": entry.calories,
            }
            for item, entry in zip(missing, entries)
        ]
        return render_template(
            "edit_calories.html",
            recipe=recipe,
            items=items,
            single_mode=False,
            return_to="",
            error=None,
        )
    except ExtractionError as e:
        logger.info("AI calorie prefill failed: %s", e)
        return render_template(
            "edit_calories.html",
            recipe=recipe,
            items=_missing_items(recipe),
            single_mode=False,
            return_to="",
            error_label="Could not pre-fill with AI",
            error=str(e),
        )
    except Exception as e:
        logger.exception("AI calorie prefill failed")
        return render_template(
            "edit_calories.html",
            recipe=recipe,
            items=_missing_items(recipe),
            single_mode=False,
            return_to="",
            error_label="Could not pre-fill with AI",
            error=str(e),
        )


@bp.route("/recipes/<recipe_id>/ingredients/quantities")
def edit_ingredient_quantities(recipe_id: str) -> Response | WerkzeugResponse | str:
    recipe = get_recipe(recipe_id)
    if recipe is None or recipe.record_type == RECORD_TYPE_IDEA:
        abort(404)
    unparseable = list_unparseable_for_recipe(recipe)
    needs_servings = servings_needs_fix(recipe)
    if not unparseable and not needs_servings:
        return redirect(url_for("recipes.edit_calories", recipe_id=recipe_id))
    return render_template(
        "edit_ingredient_quantities.html",
        recipe=recipe,
        unparseable=unparseable,
        needs_servings=needs_servings,
        error=None,
    )


@bp.route("/recipes/<recipe_id>/ingredients/quantities", methods=["POST"])
def save_ingredient_quantities(recipe_id: str) -> Response | WerkzeugResponse | str:
    recipe = get_recipe(recipe_id)
    if recipe is None or recipe.record_type == RECORD_TYPE_IDEA:
        abort(404)

    def _render_error(error: str) -> str:
        return render_template(
            "edit_ingredient_quantities.html",
            recipe=recipe,
            unparseable=list_unparseable_for_recipe(recipe),
            needs_servings=servings_needs_fix(recipe),
            error=error,
        )

    try:
        form = IngredientQuantityForm.from_form(request.form)
        updated_ingredients = list(recipe.ingredients)
        for entry in form.entries:
            index = entry["index"]
            if index < 0 or index >= len(updated_ingredients):
                raise ValueError("Invalid ingredient reference")
            updated_ingredients[index] = updated_ingredients[index].model_copy(
                update={"quantity": entry["quantity"], "unit": entry["unit"]}
            )
        update_fields: dict[str, object] = {"ingredients": updated_ingredients}
        if form.servings is not None:
            update_fields["servings"] = form.servings
        update_recipe(recipe_id, recipe.model_copy(update=update_fields))
        return redirect(url_for("recipes.edit_calories", recipe_id=recipe_id))
    except ValidationError as e:
        logger.info("Saving ingredient quantities failed validation")
        return _render_error(first_error_msg(e))
    except ValueError as e:
        logger.info("Saving ingredient quantities failed validation")
        return _render_error(str(e))
    except Exception as e:
        logger.exception("Saving ingredient quantities failed")
        return _render_error(str(e))


@bp.route("/recipes/<recipe_id>/calories/edit", methods=["POST"])
def save_calories(recipe_id: str) -> Response | WerkzeugResponse | str:
    recipe = get_recipe(recipe_id)
    if recipe is None or recipe.record_type == RECORD_TYPE_IDEA:
        abort(404)

    scope_name = request.args.get("name", "").strip()
    scope_unit = request.args.get("unit", "").strip() or None
    return_to = request.args.get("return_to", "").strip()
    single_mode = bool(scope_name)

    def _items_for_error() -> list[dict[str, object]]:
        if single_mode:
            return [_single_ingredient_item(scope_name, scope_unit)]
        return _missing_items(recipe)

    def _success_redirect() -> WerkzeugResponse:
        if return_to == "breakdown":
            return redirect(url_for("recipes.breakdown", recipe_id=recipe_id))
        return redirect(url_for("recipes.detail", recipe_id=recipe_id))

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
        return _success_redirect()
    except ValidationError as e:
        logger.info("Saving calorie info failed validation")
        return render_template(
            "edit_calories.html",
            recipe=recipe,
            items=_items_for_error(),
            single_mode=single_mode,
            return_to=return_to,
            error=first_error_msg(e),
        )
    except Exception as e:
        logger.exception("Saving calorie info failed")
        return render_template(
            "edit_calories.html",
            recipe=recipe,
            items=_items_for_error(),
            single_mode=single_mode,
            return_to=return_to,
            error=str(e),
        )


@bp.route("/recipes/add")
def add() -> str:
    return render_template("add.html")


@bp.route("/recipes/add/from-link")
def add_from_link() -> str:
    return render_template("add_from_link.html")


@bp.route("/recipes/add/from-photo")
def add_from_photo() -> str:
    return render_template("add_from_photo.html")


@bp.route("/recipes/add/idea")
def add_idea() -> str:
    return render_template(
        "add_idea.html",
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
