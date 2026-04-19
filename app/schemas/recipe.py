"""Pydantic models for recipe data."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_RECIPE_TAGS: list[str] = [
    "African",
    "American",
    "British",
    "Caribbean",
    "Chinese",
    "East-Asian",
    "European",
    "French",
    "Greek",
    "Indian",
    "Italian",
    "Japanese",
    "Korean",
    "Latin-American",
    "Mediterranean",
    "Mexican",
    "Middle-Eastern",
    "South-Asian",
    "Southeast-Asian",
    "Spanish",
    "Thai",
    "Vietnamese",
]

ALLOWED_RECIPE_TAGS_SET: frozenset[str] = frozenset(ALLOWED_RECIPE_TAGS)

RecipeTag = Literal[
    "African",
    "American",
    "British",
    "Caribbean",
    "Chinese",
    "East-Asian",
    "European",
    "French",
    "Greek",
    "Indian",
    "Italian",
    "Japanese",
    "Korean",
    "Latin-American",
    "Mediterranean",
    "Mexican",
    "Middle-Eastern",
    "South-Asian",
    "Southeast-Asian",
    "Spanish",
    "Thai",
    "Vietnamese",
]

RecordType = Literal["recipe", "idea"]
RECORD_TYPE_RECIPE: RecordType = "recipe"
RECORD_TYPE_IDEA: RecordType = "idea"


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    trimmed = value.strip()
    return trimmed or None


def _clean_required(value: Any, field_label: str) -> str:
    cleaned = _clean_optional(value)
    if cleaned is None:
        raise ValueError(f"{field_label} is required")
    return cleaned


class Ingredient(BaseModel):
    quantity: str | None = Field(
        default=None,
        description="Amount, e.g. '2' or '1/2'.",
    )
    unit: str | None = Field(
        default=None,
        description="Unit of measurement, e.g. 'cups', 'tbsp', 'g'.",
    )
    name: str = Field(description="Ingredient name, e.g. 'plain flour'.")
    notes: str | None = Field(
        default=None,
        description="Optional preparation notes, e.g. 'finely chopped'.",
    )

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def coerce_shape(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data}
        if isinstance(data, dict):
            return data
        raise ValueError("Each ingredient must be a string or object")

    @field_validator("quantity", "unit", "notes", mode="before")
    @classmethod
    def clean_optional(cls, value: Any) -> str | None:
        return _clean_optional(value)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: Any) -> str:
        return _clean_required(value, "Ingredient name")


class Step(BaseModel):
    step_number: int = Field(default=0, description="1-based position in the recipe.")
    instruction: str = Field(description="What to do at this step.")

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def coerce_shape(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"instruction": data}
        if isinstance(data, dict):
            return data
        raise ValueError("Each step must be a string or object")

    @field_validator("instruction", mode="before")
    @classmethod
    def clean_instruction(cls, value: Any) -> str:
        return _clean_required(value, "Step instruction")


class Recipe(BaseModel):
    """Internal recipe representation used by storage and routes.

    Tags are free-form strings here because legacy recipes and recipe ideas
    may carry non-cuisine tags. The cuisine-tag enum is enforced at the
    extraction and form layers instead.
    """

    record_type: RecordType = Field(
        default=RECORD_TYPE_RECIPE,
        description="'recipe' for a full recipe, 'idea' for a stub.",
    )
    title: str = Field(description="The name of the recipe.")
    description: str | None = Field(
        default=None,
        description="A brief description or introduction to the recipe.",
    )
    servings: str | None = Field(
        default=None,
        description="Number of servings, e.g. '4' or 'Serves 4-6'.",
    )
    prep_time: str | None = Field(
        default=None,
        description="Preparation time, e.g. '15 mins'.",
    )
    cook_time: str | None = Field(
        default=None,
        description="Cooking time, e.g. '30 mins'.",
    )
    total_time: str | None = Field(
        default=None,
        description="Total time from start to finish.",
    )
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    id: str | None = None
    source_type: str | None = None
    source_ref: str | None = None
    calories_per_serving: float | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("record_type", mode="before")
    @classmethod
    def default_record_type(cls, value: Any) -> Any:
        if value is None:
            return RECORD_TYPE_RECIPE
        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                return RECORD_TYPE_RECIPE
            return trimmed
        return value

    @field_validator("record_type", mode="after")
    @classmethod
    def check_record_type(cls, value: str) -> str:
        if value not in ("recipe", "idea"):
            raise ValueError("Record type must be 'recipe' or 'idea'")
        return value

    @field_validator("title", mode="before")
    @classmethod
    def clean_title(cls, value: Any) -> str:
        return _clean_required(value, "Title")

    @field_validator(
        "description",
        "servings",
        "prep_time",
        "cook_time",
        "total_time",
        mode="before",
    )
    @classmethod
    def clean_optional_strings(cls, value: Any) -> str | None:
        return _clean_optional(value)

    @field_validator("ingredients", mode="before")
    @classmethod
    def ensure_ingredients_is_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Ingredients must be a list")
        return value

    @field_validator("steps", mode="before")
    @classmethod
    def ensure_steps_is_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Steps must be a list")
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def clean_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Tags must be a list")
        cleaned: list[str] = []
        for raw in value:
            tag = _clean_optional(raw)
            if tag is not None:
                cleaned.append(tag)
        return cleaned

    @model_validator(mode="after")
    def renumber_and_require(self) -> "Recipe":
        for index, step in enumerate(self.steps, start=1):
            step.step_number = index
        if self.record_type == RECORD_TYPE_RECIPE:
            if not self.ingredients:
                raise ValueError("At least one ingredient is required")
            if not self.steps:
                raise ValueError("At least one step is required")
        return self


class ExtractedRecipe(BaseModel):
    """Recipe structure Claude returns when extracting from a URL or image.

    This model is used exclusively to generate the JSON schema sent to Claude
    as the `extract_recipe` tool input. Tags are constrained to the cuisine
    enum so Claude picks from the allowed list.
    """

    title: str = Field(description="The name of the recipe.")
    description: str | None = Field(
        default=None,
        description="A brief description or introduction to the recipe.",
    )
    servings: str | None = Field(
        default=None,
        description="Number of servings, e.g. '4' or 'Serves 4-6'.",
    )
    prep_time: str | None = Field(
        default=None,
        description="Preparation time, e.g. '15 mins'.",
    )
    cook_time: str | None = Field(
        default=None,
        description="Cooking time, e.g. '30 mins'.",
    )
    total_time: str | None = Field(
        default=None,
        description="Total time from start to finish.",
    )
    ingredients: list[Ingredient] = Field(description="List of ingredients.")
    steps: list[Step] = Field(description="Ordered list of recipe steps.")
    tags: list[RecipeTag] = Field(
        default_factory=list,
        description=(
            "Cuisine tags only. Use zero or more values from the allowed cuisine list."
        ),
    )

    model_config = ConfigDict(extra="ignore")


class _EditRecipeBody(BaseModel):
    """Recipe structure inside the edit_recipe tool payload (free-form tags)."""

    title: str = Field(description="The name of the recipe.")
    description: str | None = Field(
        default=None,
        description="A brief description or introduction to the recipe.",
    )
    servings: str | None = Field(
        default=None,
        description="Number of servings, e.g. '4' or 'Serves 4-6'.",
    )
    prep_time: str | None = Field(
        default=None,
        description="Preparation time, e.g. '15 mins'.",
    )
    cook_time: str | None = Field(
        default=None,
        description="Cooking time, e.g. '30 mins'.",
    )
    total_time: str | None = Field(
        default=None,
        description="Total time from start to finish.",
    )
    ingredients: list[Ingredient] = Field(description="List of ingredients.")
    steps: list[Step] = Field(description="Ordered list of recipe steps.")
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags describing the recipe.",
    )

    model_config = ConfigDict(extra="ignore")


class EditedRecipe(BaseModel):
    """Payload Claude returns when editing a recipe via the edit_recipe tool."""

    recipe: _EditRecipeBody
    change_summary: str = Field(
        description="Short summary of the changes that were made.",
    )
    warnings: list[str] = Field(
        description="Optional warnings or assumptions made while applying the edit.",
    )

    model_config = ConfigDict(extra="ignore")
