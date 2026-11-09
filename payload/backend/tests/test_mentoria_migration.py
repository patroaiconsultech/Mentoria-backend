"""Additive migration and guarded downgrade on a temporary SQLite schema.

PostgreSQL rehearsal is still mandatory before migration authorization.
"""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_mentoria_migration_upgrade_and_no_data_loss_downgrade(monkeypatch):
    migration_path = Path(__file__).resolve().parents[1] / "migrations/versions/017_mentoria_workshop.py"
    spec = importlib.util.spec_from_file_location("mentoria_migration_017", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table("tenants", metadata, sa.Column("id", sa.String(64), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        monkeypatch.setattr(module, "op", Operations(ctx))
        module.upgrade()

        inspector = sa.inspect(conn)
        assert inspector.has_table("mentoria_workshop_registrations")
        assert any(x["name"] == "uq_mentoria_workshop_email"
                   for x in inspector.get_unique_constraints("mentoria_workshop_registrations"))

        conn.execute(sa.text("INSERT INTO tenants(id) VALUES ('owner')"))
        conn.execute(sa.text("""
          INSERT INTO mentoria_workshop_registrations(
            id, tenant_id, workshop_slug, full_name, email_normalized,
            privacy_notice_version, privacy_accepted_at, marketing_opt_in, created_at
          ) VALUES (
            'lead-1', 'owner', 'ia-negocios-workshop', 'Example Person',
            'test@example.org', '2026-11', CURRENT_TIMESTAMP, 0, CURRENT_TIMESTAMP
          )
        """))
        with pytest.raises(RuntimeError, match="STOP_MENTORIA_DOWNGRADE_DATA_PRESENT"):
            module.downgrade()
        assert sa.inspect(conn).has_table("mentoria_workshop_registrations")

        conn.execute(sa.text("DELETE FROM mentoria_workshop_registrations"))
        module.downgrade()
        assert not sa.inspect(conn).has_table("mentoria_workshop_registrations")
