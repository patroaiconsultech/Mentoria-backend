"""Proposal-only: preflight nullable agent-scope columns before any DDL.

Not an authorization to run migrations.
"""
from alembic import op
import sqlalchemy as sa

revision = "014_thread_agent_grants"
down_revision = "013_agent_studio_control_plane"
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
        (name, sa.Column("allowed_agent_ids", sa.JSON(), nullable=True))
        for name in ("thread_participants", "thread_invitations")
    ]
    for table_name, column in _preflight_columns(desired):
        op.add_column(table_name, column)


def downgrade() -> None:
    # DESTRUCTIVE: requires independently authorized restore/reconciliation.
    op.drop_column("thread_invitations", "allowed_agent_ids")
    op.drop_column("thread_participants", "allowed_agent_ids")
