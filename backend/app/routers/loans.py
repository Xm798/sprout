import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.loan import LoanTerms, Event, amortize, DegenerateLoan

router = APIRouter(prefix="/loans")

# Fields that belong in LoanTerms (excludes start_date / interval_months which come from body).
_LOAN_TERM_KEYS = {"principal", "annual_rate", "term_count", "method"}


class AmortizationPreviewRequest(BaseModel):
    loan: dict
    anchor_date: datetime.date
    interval_count: int = 1
    events: list[dict] = []


@router.post("/amortization")
def amortization_preview(body: AmortizationPreviewRequest) -> dict:
    """Stateless amortization preview — no persistence."""
    try:
        loan_data = {k: v for k, v in body.loan.items() if k in _LOAN_TERM_KEYS}
        terms = LoanTerms(
            **loan_data,
            start_date=body.anchor_date,
            interval_months=body.interval_count,
        )
        events = [Event(**e) for e in body.events]
        rows = amortize(terms, events)
    except DegenerateLoan as exc:
        raise HTTPException(422, str(exc))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc))

    if not rows:
        raise HTTPException(422, "loan produced no installments")

    serialized = [
        {
            "seq": r.seq,
            "due_date": r.due_date.isoformat(),
            "principal": str(r.principal),
            "interest": str(r.interest),
            "payment": str(r.payment),
            "balance_after": str(r.balance_after),
            "is_prepayment": r.is_prepayment,
            "event_id": r.event_id,
        }
        for r in rows
    ]

    total_interest = sum(r.interest for r in rows)
    return {
        "rows": serialized,
        "total_interest": str(total_interest),
        "payoff_date": rows[-1].due_date.isoformat(),
    }
