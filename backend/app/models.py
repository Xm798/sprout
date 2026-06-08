import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Numeric, UniqueConstraint
from sqlmodel import SQLModel, Field

AMOUNT = lambda nullable: Column(Numeric(20, 8), nullable=nullable)  # noqa: E731


class Schedule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    narration: str = ""
    amount: Decimal = Field(sa_column=AMOUNT(False))
    currency: str
    from_account: str
    to_account: str
    interval_unit: str  # day | week | month | quarter | year
    interval_count: int = 1
    anchor_date: datetime.date
    end_date: Optional[datetime.date] = None
    max_count: Optional[int] = None
    tags: str = ""  # comma-separated tag names (no '#')
    status: str = "active"  # active | paused
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)


class Occurrence(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("schedule_id", "due_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    schedule_id: int = Field(foreign_key="schedule.id", index=True)
    due_date: datetime.date
    status: str = "pending"  # pending | confirmed | skipped
    override_amount: Optional[Decimal] = Field(default=None, sa_column=AMOUNT(True))
    override_date: Optional[datetime.date] = None
    override_narration: Optional[str] = None
    written_path: Optional[str] = None
    sprout_id: Optional[str] = None
    confirmed_at: Optional[datetime.datetime] = None
