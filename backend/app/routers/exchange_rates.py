import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.db import get_session
from app import exchange_rates as ex

router = APIRouter(prefix="/exchange-rates")


@router.get("/rate", response_model=ex.RateQuote)
def rate(
    base: str = Query(..., description="currency being priced, e.g. HKD or BTC"),
    quote: str = Query(..., description="currency to price it in, e.g. CNY"),
    on: Optional[datetime.date] = Query(None, description="rate date; defaults to today"),
    session: Session = Depends(get_session),
) -> ex.RateQuote:
    try:
        return ex.get_rate(session, base, quote, on)
    except ex.RateError as exc:
        raise HTTPException(502, str(exc))
