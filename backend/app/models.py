import datetime
from typing import Optional

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlmodel import SQLModel, Field

from app.postings import Posting


class ScheduleBase(SQLModel):
    name: str          # Sprout-internal label; never written to the ledger
    payee: str = ""    # bean payee
    narration: str = ""
    interval_unit: str  # day | week | month | quarter | year
    interval_count: int = 1
    anchor_date: datetime.date
    end_date: Optional[datetime.date] = None
    max_count: Optional[int] = None
    tags: str = ""  # comma-separated tag names (no '#')
    status: str = "active"  # active | paused
    # relative .bean path under the ledger root; None = global write strategy
    target_file: Optional[str] = None


class Schedule(ScheduleBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # list[dict] of Posting payloads (Decimal amounts serialized as strings)
    postings: list[dict] = Field(
        default_factory=list,
        sa_column=Column(MutableList.as_mutable(JSON), nullable=False),
    )
    kind: str = "fixed"  # fixed | loan
    loan: Optional[dict] = Field(
        default=None,
        sa_column=Column(MutableDict.as_mutable(JSON), nullable=True),
    )
    events: list[dict] = Field(
        default_factory=list,
        sa_column=Column(MutableList.as_mutable(JSON), nullable=False),
    )
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)


class ScheduleCreate(ScheduleBase):
    postings: list[Posting]
    kind: str = "fixed"
    loan: Optional[dict] = None
    events: list[dict] = Field(default_factory=list)


class ScheduleRead(ScheduleBase):
    id: int
    postings: list[Posting]
    kind: str = "fixed"
    loan: Optional[dict] = None
    events: list[dict] = Field(default_factory=list)
    headline_amount: Optional[str] = None
    headline_currency: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class RateCacheEntry(SQLModel, table=True):
    """One cached exchange rate for a (base, quote, date, source) tuple.

    ``rate`` is a Decimal serialized as a string to match posting amounts.
    ``rate_date`` is the requested date (the cache key); ``effective_date`` is
    the date the rate is actually for (e.g. the prior ECB business day on a
    weekend), reported as as_of so cache hits and misses agree.
    ``fetched_at`` drives TTL: fiat (Frankfurter) is re-fetched daily, crypto
    (CoinGecko) every few minutes — see app.exchange_rates."""

    base: str = Field(primary_key=True)
    quote: str = Field(primary_key=True)
    rate_date: datetime.date = Field(primary_key=True)
    source: str = Field(primary_key=True)
    rate: str
    effective_date: datetime.date
    fetched_at: datetime.datetime


class Occurrence(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("schedule_id", "due_date", "loan_event", "event_id"),)

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
    # Indexed: materialization probes existence by sprout_id for every past
    # installment on every inbox fetch.
    sprout_id: Optional[str] = Field(default=None, index=True)
    confirmed_at: Optional[datetime.datetime] = None
    loan_seq: Optional[int] = None
    loan_event: str = "regular"  # non-null sentinel; part of widened unique constraint
    event_id: str = ""           # non-null sentinel; part of widened unique constraint
    frozen_postings: Optional[list] = Field(
        default=None,
        sa_column=Column(MutableList.as_mutable(JSON), nullable=True),
    )


class NotificationLog(SQLModel, table=True):
    """One row per (occurrence, channel) successfully reminded — the dedup ledger."""
    __table_args__ = (UniqueConstraint("occurrence_id", "channel_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    occurrence_id: int = Field(foreign_key="occurrence.id", index=True)
    channel_id: str
    sent_at: datetime.datetime = Field(default_factory=datetime.datetime.now)


class OccurrenceRead(SQLModel):
    """API-facing view of an occurrence. Excludes frozen_postings (an internal
    posting snapshot) while exposing the loan fields the frontend consumes."""

    id: int
    schedule_id: int
    due_date: datetime.date
    status: str
    override_amounts: dict[str, str] = Field(default_factory=dict)
    override_date: Optional[datetime.date] = None
    override_narration: Optional[str] = None
    written_path: Optional[str] = None
    sprout_id: Optional[str] = None
    confirmed_at: Optional[datetime.datetime] = None
    loan_seq: Optional[int] = None
    loan_event: str = "regular"
    event_id: str = ""
