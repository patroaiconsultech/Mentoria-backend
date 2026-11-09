"""Proposal-only: preflight nullable access-expiry fields before any DDL.

No automatic data rewrite or historical grant modification.
"""
from alembic import op
import sqlalchemy as sa

revision = "016_thread_participant_access_expiry"
down_revision = "015_thread_collaboration_capabilities"
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

def _duration_constraint_missing() -> bool:
    name = "ck_thread_invitation_access_duration"
    inspector = sa.inspect(op.get_bind())
    checks = [
        row for row in inspector.get_check_constraints("thread_invitations")
        if row.get("name") == name
    ]
    if not checks:
        return True
    sql = " ".join(str(checks[0].get("sqltext", "")).lower().split())
    normalized = "".join(char for char in sql if char not in " ()")
    accepted = {
        "access_duration_hoursbetween1and8760",
        "access_duration_hours>=1andaccess_duration_hours<=8760",
    }
    if normalized not in accepted:
        raise RuntimeError("STOP_CONSTRAINT_CONTRACT_MISMATCH:" + name)
    return False


def upgrade() -> None:
    desired = [
        ("thread_invitations", sa.Column("access_duration_hours", sa.Integer(), nullable=True)),
        ("thread_participants", sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True)),
    ]
    missing = _preflight_columns(desired)
    need_check = _duration_constraint_missing()
    for table_name, column in missing:
        op.add_column(table_name, column)
    if need_check:
        op.create_check_constraint(
            "ck_thread_invitation_access_duration",
            "thread_invitations",
            "access_duration_hours BETWEEN 1 AND 8760",
        )


def downgrade() -> None:
    # DESTRUCTIVE: requires independently authorized restore/reconciliation.
    op.drop_constraint(
        "ck_thread_invitation_access_duration", "thread_invitations", type_="check"
    )
    op.drop_column("thread_participants", "access_expires_at")
    op.drop_column("thread_invitations", "access_duration_hours")
