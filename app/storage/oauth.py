"""OAuth client, authorization code and token storage backed by SQLite.

Secrets (client secrets, codes, access and refresh tokens) are stored only as
SHA-256 hashes; the plaintext values are returned once to the caller.
"""

import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass

from .db import get_db

CODE_TTL_SECONDS = 5 * 60
ACCESS_TOKEN_TTL_SECONDS = 60 * 60
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
# Registration is open, so unused registrations are pruned after a day.
UNAPPROVED_CLIENT_TTL_SECONDS = 24 * 60 * 60
MAX_CLIENTS = 200


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> int:
    return int(time.time())


@dataclass(frozen=True)
class Client:
    client_id: str
    client_name: str | None
    redirect_uris: list[str]
    auth_method: str
    client_secret_hash: str | None

    def check_secret(self, secret: str | None) -> bool:
        if self.client_secret_hash is None:
            return False
        return secret is not None and secrets.compare_digest(
            _hash(secret), self.client_secret_hash
        )


@dataclass(frozen=True)
class AuthorizationCode:
    client_id: str
    redirect_uri: str
    code_challenge: str
    scope: str
    resource: str


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str


@dataclass(frozen=True)
class Grant:
    id: int
    client_id: str
    client_name: str | None
    scope: str
    created_at: int
    last_used_at: int | None


def _row_to_client(row: sqlite3.Row) -> Client:
    return Client(
        client_id=row["client_id"],
        client_name=row["client_name"],
        redirect_uris=json.loads(row["redirect_uris"]),
        auth_method=row["auth_method"],
        client_secret_hash=row["client_secret_hash"],
    )


def register_client(
    client_name: str | None, redirect_uris: list[str], auth_method: str
) -> tuple[Client, str | None] | None:
    """Register a client. Returns (client, plaintext secret) or None when full."""
    db = get_db()
    db.execute(
        "DELETE FROM oauth_clients WHERE approved_at IS NULL AND created_at < ?",
        (_now() - UNAPPROVED_CLIENT_TTL_SECONDS,),
    )
    (count,) = db.execute("SELECT COUNT(*) FROM oauth_clients").fetchone()
    if count >= MAX_CLIENTS:
        db.commit()
        return None

    client_id = secrets.token_urlsafe(16)
    secret = None if auth_method == "none" else secrets.token_urlsafe(32)
    db.execute(
        """
        INSERT INTO oauth_clients (
            client_id, client_secret_hash, client_name, redirect_uris, auth_method, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            client_id,
            _hash(secret) if secret else None,
            client_name,
            json.dumps(redirect_uris),
            auth_method,
            _now(),
        ),
    )
    db.commit()
    client = Client(
        client_id=client_id,
        client_name=client_name,
        redirect_uris=redirect_uris,
        auth_method=auth_method,
        client_secret_hash=_hash(secret) if secret else None,
    )
    return client, secret


def get_client(client_id: str) -> Client | None:
    row = get_db().execute(
        "SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)
    ).fetchone()
    return _row_to_client(row) if row else None


def create_code(
    client_id: str, redirect_uri: str, code_challenge: str, scope: str, resource: str
) -> str:
    code = secrets.token_urlsafe(32)
    db = get_db()
    db.execute(
        "UPDATE oauth_clients SET approved_at = ? WHERE client_id = ?",
        (_now(), client_id),
    )
    db.execute(
        """
        INSERT INTO oauth_codes (
            code_hash, client_id, redirect_uri, code_challenge, scope, resource, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _hash(code),
            client_id,
            redirect_uri,
            code_challenge,
            scope,
            resource,
            _now() + CODE_TTL_SECONDS,
        ),
    )
    db.commit()
    return code


def consume_code(code: str) -> AuthorizationCode | None:
    """Return the code's details and delete it, so it can only be used once."""
    db = get_db()
    rows = db.execute(
        "DELETE FROM oauth_codes WHERE code_hash = ? RETURNING *", (_hash(code),)
    ).fetchall()
    db.commit()
    if not rows or rows[0]["expires_at"] < _now():
        return None
    row = rows[0]
    return AuthorizationCode(
        client_id=row["client_id"],
        redirect_uri=row["redirect_uri"],
        code_challenge=row["code_challenge"],
        scope=row["scope"],
        resource=row["resource"],
    )


def _new_token_values() -> tuple[str, str, int, int]:
    now = _now()
    return (
        secrets.token_urlsafe(32),
        secrets.token_urlsafe(32),
        now + ACCESS_TOKEN_TTL_SECONDS,
        now + REFRESH_TOKEN_TTL_SECONDS,
    )


def issue_tokens(client_id: str, scope: str, resource: str) -> IssuedTokens:
    access, refresh, access_exp, refresh_exp = _new_token_values()
    db = get_db()
    db.execute(
        """
        INSERT INTO oauth_tokens (
            client_id, access_hash, access_expires_at, refresh_hash,
            refresh_expires_at, scope, resource, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (client_id, _hash(access), access_exp, _hash(refresh), refresh_exp, scope, resource, _now()),
    )
    db.commit()
    return IssuedTokens(access, refresh, ACCESS_TOKEN_TTL_SECONDS, scope)


def rotate_refresh_token(client_id: str, refresh_token: str) -> IssuedTokens | None:
    """Exchange a refresh token for a new access/refresh pair (old pair dies)."""
    access, refresh, access_exp, refresh_exp = _new_token_values()
    db = get_db()
    rows = db.execute(
        """
        UPDATE oauth_tokens
        SET access_hash = ?, access_expires_at = ?, refresh_hash = ?, refresh_expires_at = ?
        WHERE refresh_hash = ? AND client_id = ? AND refresh_expires_at >= ?
        RETURNING scope
        """,
        (_hash(access), access_exp, _hash(refresh), refresh_exp,
         _hash(refresh_token), client_id, _now()),
    ).fetchall()
    db.commit()
    if not rows:
        return None
    return IssuedTokens(access, refresh, ACCESS_TOKEN_TTL_SECONDS, rows[0]["scope"])


def validate_access_token(access_token: str, resource: str) -> bool:
    db = get_db()
    cursor = db.execute(
        """
        UPDATE oauth_tokens SET last_used_at = ?
        WHERE access_hash = ? AND access_expires_at >= ? AND resource = ?
        """,
        (_now(), _hash(access_token), _now(), resource),
    )
    db.commit()
    return cursor.rowcount == 1


def revoke_token(client_id: str, token: str) -> None:
    db = get_db()
    hashed = _hash(token)
    db.execute(
        "DELETE FROM oauth_tokens WHERE client_id = ? AND (access_hash = ? OR refresh_hash = ?)",
        (client_id, hashed, hashed),
    )
    db.commit()


def list_grants() -> list[Grant]:
    rows = get_db().execute(
        """
        SELECT t.id, t.client_id, c.client_name, t.scope, t.created_at, t.last_used_at
        FROM oauth_tokens t JOIN oauth_clients c ON c.client_id = t.client_id
        WHERE t.refresh_expires_at >= ?
        ORDER BY t.created_at DESC
        """,
        (_now(),),
    ).fetchall()
    return [Grant(**dict(row)) for row in rows]


def delete_grant(grant_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM oauth_tokens WHERE id = ?", (grant_id,))
    db.commit()
