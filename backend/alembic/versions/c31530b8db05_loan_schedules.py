"""loan schedules

Revision ID: c31530b8db05
Revises: 3410f3212aec
Create Date: 2026-07-01 22:33:41.905957

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  SQLModel column types used in other migrations


# revision identifiers, used by Alembic.
revision: str = 'c31530b8db05'
down_revision: Union[str, Sequence[str], None] = '3410f3212aec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The naming convention used by SQLModel.metadata so batch mode can resolve
# the old unnamed (schedule_id, due_date) SQLite autoindex by convention.
_NC = {
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade() -> None:
    op.add_column("schedule", sa.Column("kind", sa.String(), nullable=False, server_default="fixed"))
    op.add_column("schedule", sa.Column("loan", sa.JSON(), nullable=True))
    op.add_column("schedule", sa.Column("events", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("occurrence", sa.Column("loan_seq", sa.Integer(), nullable=True))
    op.add_column("occurrence", sa.Column("loan_event", sa.String(), nullable=False, server_default="regular"))
    op.add_column("occurrence", sa.Column("event_id", sa.String(), nullable=False, server_default=""))
    op.add_column("occurrence", sa.Column("frozen_postings", sa.JSON(), nullable=True))
    bind = op.get_bind()
    # Postgres names the original unnamed 2-col unique "occurrence_schedule_id_due_date_key";
    # SQLite batch mode resolves it via the naming convention as "uq_occurrence_schedule_id_due_date".
    old_uq = "occurrence_schedule_id_due_date_key" if bind.dialect.name == "postgresql" else "uq_occurrence_schedule_id_due_date"
    with op.batch_alter_table("occurrence", schema=None, naming_convention=_NC) as batch:
        batch.drop_constraint(old_uq, type_="unique")
        batch.create_unique_constraint(
            "uq_occurrence_schedule_id_due_date_loan_event_event_id",
            ["schedule_id", "due_date", "loan_event", "event_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    # Recreate with the dialect-correct name so a re-upgrade can drop it by the right name.
    # On PG: use the Postgres autoname so the upgrade's PG branch finds it again.
    # On SQLite: use the convention name the batch path expects.
    new_uq = "occurrence_schedule_id_due_date_key" if bind.dialect.name == "postgresql" else "uq_occurrence_schedule_id_due_date"
    with op.batch_alter_table("occurrence", schema=None, naming_convention=_NC) as batch:
        batch.drop_constraint("uq_occurrence_schedule_id_due_date_loan_event_event_id", type_="unique")
        batch.create_unique_constraint(new_uq, ["schedule_id", "due_date"])
    for col in ("frozen_postings", "event_id", "loan_event", "loan_seq"):
        op.drop_column("occurrence", col)
    for col in ("events", "loan", "kind"):
        op.drop_column("schedule", col)
