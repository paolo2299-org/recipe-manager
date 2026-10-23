"""OAuth client, authorization code and token storage backed by SQLite.

The model classes implement Authlib's mixins so its grants and endpoints can
use them directly. Secrets (client secrets, codes, access and refresh tokens)
are stored only as SHA-256 hashes.
"""

import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from authlib.oauth2.rfc6749 import AuthorizationCodeMixin, ClientMixin, TokenMixin

from .db import get_db

SCOPE = "recipes:read"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
CODE_TTL_SECONDS = 5 * 60
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
# Registration is open, so unused registrations are pruned after a day.
UNAPPROVED_CLIENT_TTL_SECONDS = 24 * 60 * 60
MAX_CLIENTS = 200


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> int:
    return int(time.time())


@dataclass(frozen=True)
class Client(ClientMixin):
    client_id: str
    client_name: str | None
    redirect_uris: list[str]
    auth_method: str
    client_secret_hash: str | None

    def get_client_id(self) -> str:
        return self.client_id

    def get_default_redirect_uri(self) -> str | None:
        return self.redirect_uris[0] if len(self.redirect_uris) == 1 else None

    def get_allowed_scope(self, scope: str | None) -> str | None:
        if scope and set(scope.split()) - {SCOPE}:
            return None
        return SCOPE

    def check_redirect_uri(self, redirect_uri: str) -> bool:
        if redirect_uri in self.redirect_uris:
            return True
        # Loopback redirects may use any port (RFC 8252 section 7.3).
        parts = urlsplit(redirect_uri)
        if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS:
            return False
        return any(
            (r.scheme, r.hostname, r.path, r.query)
            == (parts.scheme, parts.hostname, parts.path, parts.query)
            for r in map(urlsplit, self.redirect_uris)
        )

    def check_client_secret(self, client_secret: str) -> bool:
        return self.client_secret_hash is not None and secrets.compare_digest(
            _hash(client_secret), self.client_secret_hash
        )

    def check_endpoint_auth_method(self, method: str, endpoint: str) -> bool:
        return method == self.auth_method

    def check_response_type(self, response_type: str) -> bool:
        return response_type == "code"

    def check_grant_type(self, grant_type: str) -> bool:
        return grant_type in ("authorization_code", "refresh_token")


@dataclass(frozen=True)
class AuthorizationCode(AuthorizationCodeMixin):
    client_id: str
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    scope: str

    def get_redirect_uri(self) -> str:
        return self.redirect_uri

    def get_scope(self) -> str:
        return self.scope


@dataclass(frozen=True)
class Token(TokenMixin):
    id: int
    client_id: str
    scope: str
    resource: str
    access_expires_at: int
    refresh_expires_at: int

    def check_client(self, client: Client) -> bool:
        return client.client_id == self.client_id

    def get_scope(self) -> str:
        return self.scope

    def get_expires_in(self) -> int:
        return self.access_expires_at - _now()

    def is_expired(self) -> bool:
        return self.access_expires_at < _now()

    def is_revoked(self) -> bool:
        return False

    def is_refresh_token_valid(self) -> bool:
        return self.refresh_expires_at >= _now()


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


def _row_to_token(row: sqlite3.Row) -> Token:
    return Token(
        id=row["id"],
        client_id=row["client_id"],
        scope=row["scope"],
        resource=row["resource"],
        access_expires_at=row["access_expires_at"],
        refresh_expires_at=row["refresh_expires_at"],
    )


def prune_and_count_clients() -> int:
    db = get_db()
    db.execute(
        "DELETE FROM oauth_clients WHERE approved_at IS NULL AND created_at < ?",
        (_now() - UNAPPROVED_CLIENT_TTL_SECONDS,),
    )
    db.commit()
    (count,) = db.execute("SELECT COUNT(*) FROM oauth_clients").fetchone()
    return int(count)


def save_client(client_info: dict[str, Any], client_metadata: dict[str, Any]) -> Client:
    secret = client_info.get("client_secret")
    client = Client(
        client_id=client_info["client_id"],
        client_name=client_metadata.get("client_name"),
        redirect_uris=client_metadata["redirect_uris"],
        auth_method=client_metadata["token_endpoint_auth_method"],
        client_secret_hash=_hash(secret) if secret else None,
    )
    db = get_db()
    db.execute(
        """
        INSERT INTO oauth_clients (
            client_id, client_secret_hash, client_name, redirect_uris, auth_method, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            client.client_id,
            client.client_secret_hash,
            client.client_name,
            json.dumps(client.redirect_uris),
            client.auth_method,
            _now(),
        ),
    )
    db.commit()
    return client


def get_client(client_id: str) -> Client | None:
    row = get_db().execute(
        "SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)
    ).fetchone()
    return _row_to_client(row) if row else None


def save_code(
    code: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str,
) -> None:
    db = get_db()
    db.execute(
        "UPDATE oauth_clients SET approved_at = ? WHERE client_id = ?",
        (_now(), client_id),
    )
    db.execute(
        """
        INSERT INTO oauth_codes (
            code_hash, client_id, redirect_uri, code_challenge,
            code_challenge_method, scope, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _hash(code),
            client_id,
            redirect_uri,
            code_challenge,
            code_challenge_method,
            scope,
            _now() + CODE_TTL_SECONDS,
        ),
    )
    db.commit()


def consume_code(code: str, client_id: str) -> AuthorizationCode | None:
    """Return the code's details and delete it, so it can only be used once."""
    db = get_db()
    rows = db.execute(
        "DELETE FROM oauth_codes WHERE code_hash = ? RETURNING *", (_hash(code),)
    ).fetchall()
    db.commit()
    if not rows or rows[0]["expires_at"] < _now() or rows[0]["client_id"] != client_id:
        return None
    row = rows[0]
    return AuthorizationCode(
        client_id=row["client_id"],
        redirect_uri=row["redirect_uri"],
        code_challenge=row["code_challenge"],
        code_challenge_method=row["code_challenge_method"],
        scope=row["scope"],
    )


def save_token(token: dict[str, Any], client_id: str, resource: str) -> None:
    now = _now()
    db = get_db()
    db.execute(
        """
        INSERT INTO oauth_tokens (
            client_id, access_hash, access_expires_at, refresh_hash,
            refresh_expires_at, scope, resource, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            client_id,
            _hash(token["access_token"]),
            now + token["expires_in"],
            _hash(token["refresh_token"]),
            now + REFRESH_TOKEN_TTL_SECONDS,
            token["scope"],
            resource,
            now,
        ),
    )
    db.commit()


def find_token(token: str, column: str) -> Token | None:
    if column not in ("access_hash", "refresh_hash"):
        raise ValueError(column)
    row = get_db().execute(
        f"SELECT * FROM oauth_tokens WHERE {column} = ?", (_hash(token),)
    ).fetchone()
    return _row_to_token(row) if row else None


def touch_token(token_id: int) -> None:
    db = get_db()
    db.execute("UPDATE oauth_tokens SET last_used_at = ? WHERE id = ?", (_now(), token_id))
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
