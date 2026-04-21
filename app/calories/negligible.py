"""Hard-coded list of ingredients whose calorie contribution is treated as zero."""

NEGLIGIBLE_INGREDIENTS: frozenset[str] = frozenset({
    "bay leaf",
    "bay leaves",
    "black pepper",
    "boiling water",
    "cayenne pepper",
    "chives",
    "cold water",
    "crushed red pepper flakes",
    "dried chives",
    "dried parsley",
    "fresh parsley",
    "freshly ground black pepper",
    "flaky sea salt",
    "ground black pepper",
    "hot water",
    "ice water",
    "kosher salt",
    "parsley",
    "pepper",
    "red pepper flakes",
    "salt",
    "sea salt",
    "table salt",
    "warm water",
    "water",
    "white pepper",
})


def is_negligible(name: str | None) -> bool:
    """Return True if the ingredient name is in the negligible-calorie allow-list."""
    if not isinstance(name, str):
        return False
    return name.strip().lower() in NEGLIGIBLE_INGREDIENTS
