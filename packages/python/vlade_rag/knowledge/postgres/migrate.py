"""Migration runner: numbered SQL files applied once, in order, as the database owner (ADR-0016).

After the migrations, the runner makes sure the application login role (the user of
``VLADE_DATABASE__URL``) exists, has the password of that URL and belongs to
``vlade_app_group``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from urllib.parse import unquote, urlsplit

import asyncpg

from vlade_rag.knowledge.postgres.db import asyncpg_dsn

_FILE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str


def load_migrations() -> list[Migration]:
    folder = resources.files("vlade_rag.knowledge.postgres") / "migrations"
    found = []
    for entry in folder.iterdir():
        match = _FILE.match(entry.name)
        if match:
            found.append(Migration(int(match.group(1)), entry.name, entry.read_text("utf-8")))
    return sorted(found, key=lambda m: m.version)


def app_credentials(app_url: str) -> tuple[str, str]:
    parts = urlsplit(asyncpg_dsn(app_url))
    user, password = unquote(parts.username or ""), unquote(parts.password or "")
    if not _ROLE.match(user):
        raise ValueError(f"Invalid application role name '{user}'.")
    if not password:
        raise ValueError("The application database URL must contain a password.")
    return user, password


async def upgrade(owner_url: str, app_url: str | None = None) -> list[str]:
    """Apply pending migrations. Returns the names of the applied files."""
    conn = await asyncpg.connect(asyncpg_dsn(owner_url))
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS vlade_schema_migrations ("
            " version int PRIMARY KEY, name text NOT NULL,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        applied = {
            r["version"] for r in await conn.fetch("SELECT version FROM vlade_schema_migrations")
        }
        done = []
        for migration in load_migrations():
            if migration.version in applied:
                continue
            async with conn.transaction():
                await conn.execute(migration.sql)
                await conn.execute(
                    "INSERT INTO vlade_schema_migrations (version, name) VALUES ($1, $2)",
                    migration.version,
                    migration.name,
                )
            done.append(migration.name)
        if app_url:
            await ensure_app_role(conn, app_url)
        return done
    finally:
        await conn.close()


async def ensure_app_role(conn: asyncpg.Connection, app_url: str) -> None:
    user, password = app_credentials(app_url)
    exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", user)
    quoted_user = await conn.fetchval("SELECT quote_ident($1)", user)
    quoted_password = await conn.fetchval("SELECT quote_literal($1)", password)
    verb = "ALTER" if exists else "CREATE"
    await conn.execute(f"{verb} ROLE {quoted_user} LOGIN PASSWORD {quoted_password}")
    await conn.execute(f"GRANT vlade_app_group TO {quoted_user}")


async def current_version(url: str) -> int:
    conn = await asyncpg.connect(asyncpg_dsn(url))
    try:
        exists = await conn.fetchval("SELECT to_regclass('vlade_schema_migrations') IS NOT NULL")
        if not exists:
            return 0
        return int(
            await conn.fetchval("SELECT coalesce(max(version), 0) FROM vlade_schema_migrations")
        )
    finally:
        await conn.close()
