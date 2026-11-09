"""Provisional migration 019: isolated DDL rehearsal (not PostgreSQL proof)."""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.config import Config
from alembic.script import ScriptDirectory

from orkio_v2.mentoria.persistence_models import MentoriaWebhookInbox


def migration_module():
    path = Path(__file__).resolve().parents[1] / "migrations/versions/019_mentoria_webhook_inbox.py"
    spec = spec_from_file_location("mentoria_019_test_module", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_019_is_single_provisional_head():
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root/"alembic.ini"))
    cfg.set_main_option("script_location", str(root/"migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["019_mentoria_webhook_inbox"]
    assert script.get_revision("019_mentoria_webhook_inbox").down_revision == "018_mentoria_core"


@pytest.fixture
def isolated_ddl():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.exec_driver_sql("CREATE TABLE tenants (id VARCHAR(64) PRIMARY KEY)")
        conn.exec_driver_sql("""
          CREATE TABLE mentoria_payment_attempts (
            id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
            provider VARCHAR(40) NOT NULL,
            UNIQUE (tenant_id, id, provider)
          )
        """)
        op = Operations(MigrationContext.configure(conn))
        module = migration_module()
        module.op = op
        module.upgrade()
    yield engine
    engine.dispose()


def test_019_additive_create_and_empty_downgrade(isolated_ddl):
    engine = isolated_ddl
    with engine.begin() as conn:
        assert sa.inspect(conn).has_table("mentoria_webhook_inbox")
        checks = {v["name"] for v in sa.inspect(conn).get_check_constraints("mentoria_webhook_inbox")}
        assert {"ck_mt_inbox_status", "ck_mt_inbox_attempts"} <= checks
        op = Operations(MigrationContext.configure(conn))
        module = migration_module()
        module.op = op
        module.downgrade()
        assert not sa.inspect(conn).has_table("mentoria_webhook_inbox")


def test_019_data_safe_downgrade_refusal(isolated_ddl):
    engine = isolated_ddl
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO tenants (id) VALUES ('t1')")
        conn.exec_driver_sql("""
           INSERT INTO mentoria_payment_attempts (id, tenant_id, provider)
           VALUES ('a1','t1','asaas')
        """)
        conn.execute(sa.text("""
          INSERT INTO mentoria_webhook_inbox
          (id,tenant_id,provider,provider_event_id,payment_attempt_id,
           payment_id,event_type,event_fingerprint,status,attempt_count,
           received_at,next_attempt_at)
          VALUES ('id','t1','asaas','evt','a1','pay','PAYMENT_RECEIVED',
                  :fingerprint,'PENDING',0,:now,:now)
        """), {"fingerprint":"a"*64,"now":"2026-11-08T12:00:00+00:00"})
        op = Operations(MigrationContext.configure(conn))
        module = migration_module()
        module.op = op
        with pytest.raises(RuntimeError, match="HAS_DURABLE_RECEIPTS"):
            module.downgrade()
        assert conn.scalar(sa.text("SELECT COUNT(*) FROM mentoria_webhook_inbox")) == 1


def test_019_orm_ddl_columns_agree():
    expected = {col.name for col in MentoriaWebhookInbox.__table__.columns}
    mig = migration_module()
    # Python source only, no DDL execution here
    body = Path(mig.__file__).read_text()
    for name in expected:
        assert f'"{name}"' in body
