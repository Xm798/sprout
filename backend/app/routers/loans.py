import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.loan import (
    Event, amortize, DegenerateLoan, loan_terms_from_dict, installment_to_dict,
)

router = APIRouter(prefix="/loans")


class AmortizationPreviewRequest(BaseModel):
    loan: dict
    anchor_date: datetime.date
    interval_count: int = 1
    events: list[dict] = []


@router.post("/amortization")
def amortization_preview(body: AmortizationPreviewRequest) -> dict:
    """Stateless amortization preview — no persistence."""
    try:
        if not 1 <= body.interval_count <= 12:
            raise ValueError("interval_count must be between 1 and 12")
        terms = loan_terms_from_dict(body.loan, body.anchor_date, body.interval_count)
        if not 1 <= terms.term_count <= 1200:
            raise ValueError("term_count must be between 1 and 1200")
        events = [Event(**e) for e in body.events]
        rows = amortize(terms, events)
    except DegenerateLoan as exc:
        raise HTTPException(422, str(exc))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc))

    if not rows:
        raise HTTPException(422, "loan produced no installments")

    serialized = [installment_to_dict(r) for r in rows]
    total_interest = sum(r.interest for r in rows)
    return {
        "rows": serialized,
        "total_interest": str(total_interest),
        "payoff_date": rows[-1].due_date.isoformat(),
    }
