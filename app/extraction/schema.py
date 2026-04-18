"""Single source of truth for the recipe extraction tool schema."""

ALLOWED_RECIPE_TAGS = [
    "African",
    "American",
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

EXTRACT_RECIPE_TOOL = {
    "name": "extract_recipe",
    "description": "Extract structured recipe information.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The name of the recipe.",
            },
            "description": {
                "type": "string",
                "description": "A brief description or introduction to the recipe.",
            },
            "servings": {
                "type": "string",
                "description": "Number of servings, e.g. '4' or 'Serves 4-6'.",
            },
            "prep_time": {
                "type": "string",
                "description": "Preparation time, e.g. '15 mins'.",
            },
            "cook_time": {
                "type": "string",
                "description": "Cooking time, e.g. '30 mins'.",
            },
            "total_time": {
                "type": "string",
                "description": "Total time from start to finish.",
            },
            "ingredients": {
                "type": "array",
                "description": "List of ingredients.",
                "items": {
                    "type": "object",
                    "properties": {
                        "quantity": {
                            "type": "string",
                            "description": "Amount, e.g. '2' or '1/2'.",
                        },
                        "unit": {
                            "type": "string",
                            "description": "Unit of measurement, e.g. 'cups', 'tbsp', 'g'.",
                        },
                        "name": {
                            "type": "string",
                            "description": "Ingredient name, e.g. 'plain flour'.",
                        },
                        "notes": {
                            "type": "string",
                            "description": "Optional preparation notes, e.g. 'finely chopped'.",
                        },
                    },
                    "required": ["name"],
                },
            },
            "steps": {
                "type": "array",
                "description": "Ordered list of recipe steps.",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_number": {"type": "integer"},
                        "instruction": {"type": "string"},
                    },
                    "required": ["step_number", "instruction"],
                },
            },
            "tags": {
                "type": "array",
                "description": (
                    "Cuisine tags only. Use zero or more values from the allowed cuisine list."
                ),
                "items": {
                    "type": "string",
                    "enum": ALLOWED_RECIPE_TAGS,
                },
            },
        },
        "required": ["title", "ingredients", "steps"],
    },
}

EDIT_RECIPE_TOOL = {
    "name": "edit_recipe",
    "description": "Edit an existing structured recipe based on a natural language request.",
    "input_schema": {
        "type": "object",
        "properties": {
            "recipe": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The name of the recipe.",
                    },
                    "description": {
                        "type": "string",
                        "description": "A brief description or introduction to the recipe.",
                    },
                    "servings": {
                        "type": "string",
                        "description": "Number of servings, e.g. '4' or 'Serves 4-6'.",
                    },
                    "prep_time": {
                        "type": "string",
                        "description": "Preparation time, e.g. '15 mins'.",
                    },
                    "cook_time": {
                        "type": "string",
                        "description": "Cooking time, e.g. '30 mins'.",
                    },
                    "total_time": {
                        "type": "string",
                        "description": "Total time from start to finish.",
                    },
                    "ingredients": {
                        "type": "array",
                        "description": "List of ingredients.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "quantity": {
                                    "type": "string",
                                    "description": "Amount, e.g. '2' or '1/2'.",
                                },
                                "unit": {
                                    "type": "string",
                                    "description": "Unit of measurement, e.g. 'cups', 'tbsp', 'g'.",
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Ingredient name, e.g. 'plain flour'.",
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Optional preparation notes, e.g. 'finely chopped'.",
                                },
                            },
                            "required": ["name"],
                        },
                    },
                    "steps": {
                        "type": "array",
                        "description": "Ordered list of recipe steps.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_number": {"type": "integer"},
                                "instruction": {"type": "string"},
                            },
                            "required": ["step_number", "instruction"],
                        },
                    },
                    "tags": {
                        "type": "array",
                        "description": "Free-form tags describing the recipe.",
                        "items": {
                            "type": "string",
                        },
                    },
                },
                "required": ["title", "ingredients", "steps"],
            },
            "change_summary": {
                "type": "string",
                "description": "Short summary of the changes that were made.",
            },
            "warnings": {
                "type": "array",
                "description": "Optional warnings or assumptions made while applying the edit.",
                "items": {
                    "type": "string",
                },
            },
        },
        "required": ["recipe", "change_summary", "warnings"],
    },
}
