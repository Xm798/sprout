"""index occurrence sprout_id

Revision ID: d4e7a1c9f2b8
Revises: c31530b8db05
Create Date: 2026-07-02 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  SQLModel column types used in other migrations


# revision identifiers, used by Alembic.
revision: str = 'd4e7a1c9f2b8'
down_revision: Union[str, Sequence[str], None] = 'c31530b8db05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Materialization probes occurrence existence by sprout_id for every past
    # installment on every inbox fetch; without this index each probe is a full
    # table scan.
    op.create_index("ix_occurrence_sprout_id", "occurrence", ["sprout_id"])


def downgrade() -> None:
    op.drop_index("ix_occurrence_sprout_id", table_name="occurrence")
