from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Schedule, ScheduleCreate

router = APIRouter(prefix="/schedules")


@router.post("", response_model=Schedule)
def create(payload: ScheduleCreate, session: Session = Depends(get_session)) -> Schedule:
    sch = Schedule(**payload.model_dump())
    session.add(sch)
    session.commit()
    session.refresh(sch)
    return sch


@router.get("", response_model=list[Schedule])
def list_all(session: Session = Depends(get_session)) -> list[Schedule]:
    return session.exec(select(Schedule)).all()


@router.get("/{schedule_id}", response_model=Schedule)
def get_one(schedule_id: int, session: Session = Depends(get_session)) -> Schedule:
    sch = session.get(Schedule, schedule_id)
    if sch is None:
        raise HTTPException(404, "schedule not found")
    return sch


@router.put("/{schedule_id}", response_model=Schedule)
def update(schedule_id: int, payload: ScheduleCreate, session: Session = Depends(get_session)) -> Schedule:
    sch = session.get(Schedule, schedule_id)
    if sch is None:
        raise HTTPException(404, "schedule not found")
    data = payload.model_dump()
    for key, value in data.items():
        setattr(sch, key, value)
    session.add(sch)
    session.commit()
    session.refresh(sch)
    return sch


@router.delete("/{schedule_id}")
def delete(schedule_id: int, session: Session = Depends(get_session)) -> dict:
    sch = session.get(Schedule, schedule_id)
    if sch is None:
        raise HTTPException(404, "schedule not found")
    session.delete(sch)
    session.commit()
    return {"ok": True}
