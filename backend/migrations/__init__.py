"""Lightweight SQL migration runner — applies numbered .sql files in order.

Tracks applied migrations in a `_migrations` table so each script runs exactly once.
Designed for the raw-DDL-per-module pattern used throughout DocSuri (accounts, library,
ingestion control-plane). No ORM dependency — works with any psycopg/SQLAlchemy connection.

Usage:
    from backend.migrations import apply_migrations
    apply_migrations(dsn, paths=["backend/modules/accounts/migrations",
                                  "backend/modules/library/migrations"])
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("docsuri.backend.migrations")

_TRACKING_DDL = """
CREATE TABLE IF NOT EXISTS _migrations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _normalize_dsn(dsn: str) -> str:
    """Strip a SQLAlchemy ``+driver`` dialect suffix so raw psycopg accepts the DSN.

    The app's DATABASE_URL is ``postgresql+psycopg://…`` (SQLAlchemy dialect form), but
    ``psycopg.connect()`` speaks plain libpq URLs and rejects the ``+driver`` scheme.
    Normalizing here lets ONE DATABASE_URL drive both the app and this runner instead of
    forcing callers to maintain two spellings of the same DSN.
    """
    scheme, sep, rest = dsn.partition("://")
    if sep and "+" in scheme:
        return scheme.split("+", 1)[0] + sep + rest
    return dsn


def apply_migrations(dsn: str, paths: list[str | Path]) -> list[str]:
    """Apply all pending migrations in order. Returns names of newly applied scripts."""
    import psycopg

    applied: list[str] = []
    with psycopg.connect(_normalize_dsn(dsn)) as conn:
        conn.execute(_TRACKING_DDL)
        conn.commit()

        already_applied = {
            row[0] for row in conn.execute("SELECT name FROM _migrations").fetchall()
        }

        for migrations_dir in paths:
            scripts = sorted(Path(migrations_dir).glob("*.sql"))
            for script in scripts:
                if script.name in already_applied:
                    continue
                log.info("applying migration: %s", script.name)
                sql = script.read_text(encoding="utf-8")
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO _migrations (name) VALUES (%s)", (script.name,)
                )
                conn.commit()
                applied.append(script.name)
                log.info("applied: %s", script.name)

    return applied


def pending_migrations(dsn: str, paths: list[str | Path]) -> list[str]:
    """List migration scripts that haven't been applied yet."""
    import psycopg

    with psycopg.connect(_normalize_dsn(dsn)) as conn:
        conn.execute(_TRACKING_DDL)
        conn.commit()
        already_applied = {
            row[0] for row in conn.execute("SELECT name FROM _migrations").fetchall()
        }

    pending: list[str] = []
    for migrations_dir in paths:
        scripts = sorted(Path(migrations_dir).glob("*.sql"))
        for script in scripts:
            if script.name not in already_applied:
                pending.append(str(script))
    return pending
