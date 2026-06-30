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

# Columns to add to appconfig, in order: (name, Column).
_APPCONFIG_COLS = [
    ("notify_enabled", sa.Column("notify_enabled", sa.Boolean(), nullable=False,
                                 server_default=sa.false())),
    ("notify_channels", sa.Column("notify_channels", sa.JSON(), nullable=False,
                                  server_default=sa.text("'[]'"))),
    ("notify_lead_days", sa.Column("notify_lead_days", sa.Integer(), nullable=False,
                                   server_default="0")),
    ("notify_time", sa.Column("notify_time", sqlmodel.sql.sqltypes.AutoString(),
                              nullable=False, server_default="08:00")),
    ("notify_timezone", sa.Column("notify_timezone", sqlmodel.sql.sqltypes.AutoString(),
                                  nullable=False, server_default="")),
]


def upgrade() -> None:
    # server_default on every NOT NULL column so ADD COLUMN works on populated DBs.
    # Guard with existence checks so the migration is idempotent when applied to a
    # DB built by SQLModel.metadata.create_all (which already has the new columns).
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_cols = {c["name"] for c in insp.get_columns("appconfig")}
    missing = [(name, col) for name, col in _APPCONFIG_COLS if name not in existing_cols]
    if missing:
        with op.batch_alter_table("appconfig") as b:
            for _name, col in missing:
                b.add_column(col)

    if "notificationlog" not in insp.get_table_names():
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
        op.create_index(op.f("ix_notificationlog_occurrence_id"), "notificationlog",
                        ["occurrence_id"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "notificationlog" in insp.get_table_names():
        op.drop_index(op.f("ix_notificationlog_occurrence_id"), table_name="notificationlog")
        op.drop_table("notificationlog")
    existing_cols = {c["name"] for c in insp.get_columns("appconfig")}
    present = [name for name, _ in reversed(_APPCONFIG_COLS) if name in existing_cols]
    if present:
        with op.batch_alter_table("appconfig") as b:
            for col in present:
                b.drop_column(col)
