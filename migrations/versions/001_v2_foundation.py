"""ORKIO v2 foundation
Revision ID: 001_v2_foundation
Revises:
"""
from alembic import op
import sqlalchemy as sa
from orkio_v2.database import Base
from orkio_v2 import models
revision="001_v2_foundation"
down_revision=None
branch_labels=None
depends_on=None
def upgrade():
    bind=op.get_bind()
    # Alembic 1.19.1 creates version_num as VARCHAR(32) by default.
    # Downstream revision IDs 015/016 exceed 32 characters.
    # Widen before Alembic records this first revision, for a fresh
    # PostgreSQL chain. A database already past 001 needs a separate gate.
    if bind.dialect.name != "postgresql":
        raise RuntimeError("STOP_SCHEMA_REHEARSAL_REQUIRES_POSTGRESQL")
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )
    Base.metadata.create_all(bind=bind)
def downgrade():
    bind=op.get_bind()
    Base.metadata.drop_all(bind=bind)
