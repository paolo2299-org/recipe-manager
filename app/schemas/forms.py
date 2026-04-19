"""Pydantic models for request form parsing and validation."""

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from werkzeug.datastructures import ImmutableMultiDict

from app.schemas.recipe import ALLOWED_RECIPE_TAGS_SET


def first_error_msg(exc: ValidationError) -> str:
    """Extract the first user-facing message from a Pydantic ValidationError.

    Strips the "Value error, " prefix that Pydantic wraps around raised
    ValueError messages so the rendered error reads naturally.
    """
    errors = exc.errors()
    if not errors:
        return str(exc)
    msg = str(errors[0].get("msg", ""))
    prefix = "Value error, "
    if msg.startswith(prefix):
        msg = msg[len(prefix):]
    return msg


def _clean_tags_strict(value: Any) -> list[str]:
    """Tag list validator: accept only entries in ALLOWED_RECIPE_TAGS_SET, dedupe, preserve order."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Tags must be a list")
    selected: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            continue
        tag = raw.strip()
        if not tag:
            continue
        if tag not in ALLOWED_RECIPE_TAGS_SET:
            raise ValueError(f"Invalid cuisine tag: {tag}")
        if tag not in selected:
            selected.append(tag)
    return selected


class IdeaForm(BaseModel):
    """Form model for creating or updating a recipe idea."""

    title: str
    description: str = ""
    tags: list[str] = []

    model_config = ConfigDict(extra="ignore")

    @field_validator("title", mode="before")
    @classmethod
    def title_required(cls, value: Any) -> str:
        trimmed = value.strip() if isinstance(value, str) else ""
        if not trimmed:
            raise ValueError("Title is required")
        return trimmed

    @field_validator("description", mode="before")
    @classmethod
    def coerce_description(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, value: Any) -> list[str]:
        return _clean_tags_strict(value)

    @classmethod
    def from_form(cls, form: ImmutableMultiDict[str, str]) -> "IdeaForm":
        return cls.model_validate(
            {
                "title": form.get("title", ""),
                "description": form.get("description", ""),
                "tags": form.getlist("tags"),
            }
        )


class CalorieBatchForm(BaseModel):
    """Form model for the per-ingredient calorie editor.

    Incoming form fields are parallel lists (name[], unit[], reference_quantity[], calories[]).
    Rows where both reference_quantity and calories are blank are dropped; rows where
    one but not the other is blank raise a validation error.
    """

    entries: list[dict[str, Any]]

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def from_form(cls, form: ImmutableMultiDict[str, str]) -> "CalorieBatchForm":
        names = form.getlist("name")
        units = form.getlist("unit")
        references = form.getlist("reference_quantity")
        calories = form.getlist("calories")

        entries: list[dict[str, Any]] = []
        for name, unit, reference, cals in zip(names, units, references, calories):
            reference_trimmed = reference.strip()
            cals_trimmed = cals.strip()
            if not reference_trimmed and not cals_trimmed:
                continue
            if not reference_trimmed or not cals_trimmed:
                raise ValueError(
                    f"Both reference quantity and calories are required for {name}"
                )
            entries.append(
                {
                    "name": name,
                    "unit": unit or None,
                    "reference_quantity": reference_trimmed,
                    "calories": cals_trimmed,
                }
            )
        return cls(entries=entries)


class ExtractUrlForm(BaseModel):
    url: str

    model_config = ConfigDict(extra="ignore")

    @field_validator("url", mode="before")
    @classmethod
    def url_required(cls, value: Any) -> str:
        trimmed = value.strip() if isinstance(value, str) else ""
        if not trimmed:
            raise ValueError("URL is required")
        return trimmed


class EditInstructionForm(BaseModel):
    instruction: str

    model_config = ConfigDict(extra="ignore")

    @field_validator("instruction", mode="before")
    @classmethod
    def instruction_required(cls, value: Any) -> str:
        trimmed = value.strip() if isinstance(value, str) else ""
        if not trimmed:
            raise ValueError("Edit instruction is required")
        return trimmed
