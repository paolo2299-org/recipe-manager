"""SQLite connection management for the recipe store."""

import os
import sqlite3

from flask import Flask, current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type          TEXT    NOT NULL DEFAULT 'recipe',
    title                TEXT    NOT NULL,
    description          TEXT,
    servings             TEXT,
    prep_time            TEXT,
    cook_time            TEXT,
    total_time           TEXT,
    ingredients          TEXT    NOT NULL,
    steps                TEXT    NOT NULL,
    tags                 TEXT    NOT NULL,
    source_type          TEXT,
    source_ref           TEXT,
    calories_per_serving REAL,
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_recipes_created_at ON recipes(created_at DESC);

CREATE TABLE IF NOT EXISTS calories (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT NOT NULL,
    unit               TEXT,
    name_key           TEXT NOT NULL,
    unit_key           TEXT NOT NULL,
    reference_quantity REAL NOT NULL,
    calories           REAL NOT NULL,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_calories_lookup ON calories(name_key, unit_key);
"""


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db() -> sqlite3.Connection:
    """Return the request-scoped SQLite connection, opening it if needed."""
    if "db" not in g:
        g.db = _connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(app: Flask) -> None:
    """Ensure the SQLite file + schema exist and wire teardown on the app."""
    path = app.config["DATABASE_PATH"]
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = _connect(path)
    try:
        conn.executescript(SCHEMA)
        if not _has_column(conn, "recipes", "record_type"):
            conn.execute(
                "ALTER TABLE recipes ADD COLUMN record_type TEXT NOT NULL DEFAULT 'recipe'"
            )
        if not _has_column(conn, "recipes", "calories_per_serving"):
            conn.execute(
                "ALTER TABLE recipes ADD COLUMN calories_per_serving REAL"
            )
        conn.commit()
    finally:
        conn.close()

    app.teardown_appcontext(close_db)
