import os
from typing import Optional

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
    lookahead_days: int = 0


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
        lookahead_days=int(os.getenv("SPROUT_LOOKAHEAD_DAYS", "0")),
    )
