"""add notifications

Revision ID: a1n0t1f1cat0
Revises: c18c6c73309d
Create Date: 2026-06-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "a1n0t1f1cat0"
down_revision: Union[str, Sequence[str], None] = "c18c6c73309d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # server_default on every NOT NULL column so ADD COLUMN works on populated DBs.
    op.add_column("appconfig", sa.Column("notify_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("appconfig", sa.Column("notify_channels", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("appconfig", sa.Column("notify_lead_days", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("appconfig", sa.Column("notify_time", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("'08:00'")))
    op.add_column("appconfig", sa.Column("notify_timezone", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("''")))
    op.create_table(
        "notificationlog",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("occurrence_id", sa.Integer(), nullable=False),
        sa.Column("channel_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["occurrence_id"], ["occurrence.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("occurrence_id", "channel_name"),
    )
    op.create_index(op.f("ix_notificationlog_occurrence_id"), "notificationlog", ["occurrence_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notificationlog_occurrence_id"), table_name="notificationlog")
    op.drop_table("notificationlog")
    for col in ("notify_timezone", "notify_time", "notify_lead_days", "notify_channels", "notify_enabled"):
        op.drop_column("appconfig", col)
