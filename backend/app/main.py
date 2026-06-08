from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers import schedules, inbox, meta

app = FastAPI(title="Sprout")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schedules.router)
app.include_router(inbox.router)
app.include_router(meta.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
