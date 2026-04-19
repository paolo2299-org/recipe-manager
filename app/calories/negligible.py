"""Hard-coded list of ingredients whose calorie contribution is treated as zero."""

NEGLIGIBLE_INGREDIENTS: frozenset[str] = frozenset({
    "water",
    "salt",
    "pepper",
    "black pepper",
    "parsley",
})


def is_negligible(name: str | None) -> bool:
    """Return True if the ingredient name is in the negligible-calorie allow-list."""
    if not isinstance(name, str):
        return False
    return name.strip().lower() in NEGLIGIBLE_INGREDIENTS
