import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles  # noqa: F401  (kept for future asset mounts)

from app.db import init_db
from app.routers import schedules, inbox, meta

app = FastAPI(title="Sprout")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schedules.router, prefix="/api")
app.include_router(inbox.router, prefix="/api")
app.include_router(meta.router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_db()


# Serve the built SPA when a static dir is present (production single-image deploy).
# Absent in dev/test, so this block is skipped there and the API tests are unaffected.
_STATIC_DIR = Path(os.getenv("SPROUT_STATIC_DIR", "static"))

if _STATIC_DIR.is_dir():

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        candidate = _STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_STATIC_DIR / "index.html")
