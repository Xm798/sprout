import os
from typing import Optional

from sqlalchemy import Column, JSON, text
from sqlalchemy.ext.mutable import MutableList
from sqlmodel import SQLModel, Field


class AppConfig(SQLModel, table=True):
    """Single-row (id=1) application configuration, editable via the API."""

    id: Optional[int] = Field(default=1, primary_key=True)
    ledger_main_file: str = ""
    ledger_root: str = ""
    write_mode: str = "single_file"  # single_file | month_file
    single_file_name: str = "sprout.bean"
    month_file_template: str = "transactions/{year}/{year}-{month:02d}.bean"
    default_tag: str = "sprout"
    default_currency: str = "USD"
    lookahead_days: int = 0

    # --- notifications ---
    notify_enabled: bool = False
    notify_channels: list[dict] = Field(
        default_factory=list,
        sa_column=Column(MutableList.as_mutable(JSON), nullable=False, server_default=text("'[]'")),
    )
    notify_lead_days: int = 0
    notify_time: str = "08:00"        # HH:MM, wall-clock in notify_timezone
    notify_timezone: str = ""          # IANA tz; "" = server local


def config_from_env() -> AppConfig:
    return AppConfig(
        id=1,
        ledger_main_file=os.getenv("SPROUT_LEDGER_MAIN_FILE", ""),
        ledger_root=os.getenv("SPROUT_LEDGER_ROOT", ""),
        write_mode=os.getenv("SPROUT_WRITE_MODE", "single_file"),
        single_file_name=os.getenv("SPROUT_SINGLE_FILE_NAME", "sprout.bean"),
        month_file_template=os.getenv(
            "SPROUT_MONTH_FILE_TEMPLATE", "transactions/{year}/{year}-{month:02d}.bean"
        ),
        default_tag=os.getenv("SPROUT_DEFAULT_TAG", "sprout"),
        default_currency=os.getenv("SPROUT_DEFAULT_CURRENCY", "USD"),
        lookahead_days=int(os.getenv("SPROUT_LOOKAHEAD_DAYS", "0")),
        notify_enabled=os.getenv("SPROUT_NOTIFY_ENABLED", "").lower() in ("1", "true", "yes"),
        notify_lead_days=int(os.getenv("SPROUT_NOTIFY_LEAD_DAYS", "0")),
        notify_time=os.getenv("SPROUT_NOTIFY_TIME", "08:00"),
        notify_timezone=os.getenv("SPROUT_NOTIFY_TIMEZONE", ""),
    )
