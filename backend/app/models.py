import datetime
from typing import Optional

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlmodel import SQLModel, Field

from app.postings import Posting


class ScheduleBase(SQLModel):
    name: str
    narration: str = ""
    interval_unit: str  # day | week | month | quarter | year
    interval_count: int = 1
    anchor_date: datetime.date
    end_date: Optional[datetime.date] = None
    max_count: Optional[int] = None
    tags: str = ""  # comma-separated tag names (no '#')
    status: str = "active"  # active | paused


class Schedule(ScheduleBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # list[dict] of Posting payloads (Decimal amounts serialized as strings)
    postings: list[dict] = Field(
        default_factory=list,
        sa_column=Column(MutableList.as_mutable(JSON), nullable=False),
    )
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)


class ScheduleCreate(ScheduleBase):
    postings: list[Posting]


class ScheduleRead(ScheduleBase):
    id: int
    postings: list[Posting]
    headline_amount: Optional[str] = None
    headline_currency: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class Occurrence(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("schedule_id", "due_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    schedule_id: int = Field(foreign_key="schedule.id", index=True)
    due_date: datetime.date
    status: str = "pending"  # pending | confirmed | skipped
    # {posting_id: amount_string} per-leg overrides
    override_amounts: dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(MutableDict.as_mutable(JSON), nullable=False),
    )
    override_date: Optional[datetime.date] = None
    override_narration: Optional[str] = None
    written_path: Optional[str] = None
    sprout_id: Optional[str] = None
    confirmed_at: Optional[datetime.datetime] = None
