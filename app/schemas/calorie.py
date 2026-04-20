"""Pydantic models for calorie entries."""

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class CalorieEntry(BaseModel):
    """A single calorie lookup row: how many calories per reference quantity of an ingredient."""

    name: str
    unit: str | None = None
    reference_quantity: float
    calories: float

    model_config = ConfigDict(extra="ignore")

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Calorie name is required")
        return value.strip()

    @field_validator("unit", mode="before")
    @classmethod
    def clean_unit(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        trimmed = value.strip()
        return trimmed or None

    @field_validator("reference_quantity", "calories", mode="before")
    @classmethod
    def coerce_float(cls, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Reference quantity and calories must be numeric") from exc

    @field_validator("reference_quantity", mode="after")
    @classmethod
    def positive_reference(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Reference quantity must be greater than zero")
        return value

    @field_validator("calories", mode="after")
    @classmethod
    def non_negative_calories(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Calories must be zero or greater")
        return value


class MissingCalorie(BaseModel):
    """An ingredient (name, unit) pair that has no calorie row yet."""

    name: str
    unit: str | None = None

    model_config = ConfigDict(extra="ignore")


class PrefilledCalories(BaseModel):
    """Claude tool payload: per-ingredient calorie suggestions in the same order as the input."""

    entries: list[CalorieEntry]

    model_config = ConfigDict(extra="ignore")


class BreakdownRow(BaseModel):
    """A single line in the per-ingredient calorie breakdown for a recipe."""

    name: str
    unit: str | None = None
    quantity: str | None = None
    per_serving_calories: float | None = None
    reference: CalorieEntry | None = None
    is_negligible: bool = False

    model_config = ConfigDict(extra="ignore")
