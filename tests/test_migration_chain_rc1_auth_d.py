"""Fail-closed regression for PostgreSQL-only Alembic foundation.

This test intentionally uses temporary SQLite only to prove rejection.
The real upgrade/downgrade and full 001-016 schema contract require
a separate, approved, disposable PostgreSQL CI job.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from orkio_v2.config import get_settings


ROOT = Path(__file__).resolve().parents[1]


def _config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def test_sqlite_rejected_before_application_schema_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'fresh-migration.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("PLATFORM_ENVIRONMENT", "test")
    monkeypatch.setenv("PLATFORM_AUTH_MODE", "test")
    monkeypatch.setenv("PLATFORM_INVITATION_TOKEN_SECRET", "x" * 40)
    monkeypatch.delenv("PLATFORM_NATIVE_AUTH_ENABLED", raising=False)
    get_settings.cache_clear()

    try:
        # Never relax the PostgreSQL guard in 001 just to make SQLite green.
        with pytest.raises(
            RuntimeError,
            match=r"^STOP_SCHEMA_REHEARSAL_REQUIRES_POSTGRESQL$",
        ):
            command.upgrade(_config(), "001_v2_foundation")

        # Alembic may create its bookkeeping table before reaching 001,
        # but must not materialize application tables or record revision 001.
        engine = sa.create_engine(database_url)
        try:
            with engine.connect() as conn:
                tables = set(sa.inspect(conn).get_table_names())
                assert tables <= {"alembic_version"}, (
                    f"SQLite unexpectedly acquired application tables: {sorted(tables)}"
                )
                if "alembic_version" in tables:
                    count = conn.exec_driver_sql(
                        "SELECT count(*) FROM alembic_version"
                    ).scalar_one()
                    assert count == 0
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()
