"""_normalize_dsn — the app's SQLAlchemy DSN must drive the raw-psycopg migration runner.

Regression for the local-serving gotcha: DATABASE_URL=postgresql+psycopg://… (the app's
dialect form) made `python -m backend.migrations` fail, forcing a second plain-libpq
spelling of the same DSN. Pure-function tests, no DB required.
"""

from backend.migrations import _normalize_dsn


def test_strips_sqlalchemy_driver_suffix():
    assert (
        _normalize_dsn("postgresql+psycopg://docsuri:docsuri@localhost:5432/docsuri")
        == "postgresql://docsuri:docsuri@localhost:5432/docsuri"
    )


def test_plain_libpq_dsn_passes_through_unchanged():
    dsn = "postgresql://docsuri:docsuri@localhost:5432/docsuri"
    assert _normalize_dsn(dsn) == dsn


def test_keyword_value_dsn_passes_through_unchanged():
    dsn = "host=localhost dbname=docsuri user=docsuri"
    assert _normalize_dsn(dsn) == dsn


def test_plus_after_scheme_is_not_touched():
    dsn = "postgresql://user:pa+ss@localhost/db"
    assert _normalize_dsn(dsn) == dsn
