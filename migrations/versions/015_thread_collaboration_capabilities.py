"""Proposal-only: preflight nullable collaboration controls before any DDL.

No grant backfill or implicit permission change.
"""
from alembic import op
import sqlalchemy as sa

revision = "015_thread_collaboration_capabilities"
down_revision = "014_thread_agent_grants"
branch_labels = None
depends_on = None

def _preflight_columns(requested):
    """Return missing columns only after every existing column has been checked."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    missing = []
    for table_name, column in requested:
        if not inspector.has_table(table_name):
            raise RuntimeError(f"STOP_REQUIRED_TABLE_MISSING:{table_name}")
        matches = [
            entry for entry in inspector.get_columns(table_name)
            if entry["name"] == column.name
        ]
        if not matches:
            missing.append((table_name, column))
            continue
        current = matches[0]
        found_type = current["type"].compile(dialect=connection.dialect).upper()
        wanted_type = column.type.compile(dialect=connection.dialect).upper()
        if (found_type != wanted_type
                or current.get("nullable") is not True
                or current.get("default") is not None):
            raise RuntimeError(
                f"STOP_COLUMN_CONTRACT_MISMATCH:{table_name}.{column.name}"
            )
    return missing

def upgrade() -> None:
    desired = [
        (table_name, sa.Column(field, sa.Boolean(), nullable=True))
        for table_name in ("thread_participants", "thread_invitations")
        for field in ("can_read_messages", "can_write_messages")
    ]
    for table_name, column in _preflight_columns(desired):
        op.add_column(table_name, column)


def downgrade() -> None:
    # DESTRUCTIVE: requires independently authorized restore/reconciliation.
    for name in ("thread_invitations", "thread_participants"):
        op.drop_column(name, "can_write_messages")
        op.drop_column(name, "can_read_messages")
