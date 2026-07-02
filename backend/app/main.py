import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.db import init_db
from app.notify import scheduler as _scheduler
from app.routers import schedules, inbox, history, meta, exchange_rates, loans


def _scheduler_enabled() -> bool:
    return os.getenv("SPROUT_ENABLE_SCHEDULER", "1").lower() not in ("0", "false", "no", "")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    enabled = _scheduler_enabled()
    if enabled:
        _scheduler.start()
    try:
        yield
    finally:
        if enabled:
            _scheduler.shutdown()


app = FastAPI(title="Sprout", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schedules.router, prefix="/api")
app.include_router(inbox.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(meta.router, prefix="/api")
app.include_router(exchange_rates.router, prefix="/api")
app.include_router(loans.router, prefix="/api")


def _safe_static_path(full_path: str, static_root: Path) -> Path:
    """Resolve ``full_path`` within ``static_root``, guarding against traversal.

    Returns the requested file only if it exists strictly inside ``static_root``;
    otherwise falls back to ``index.html`` (so SPA client-side routes resolve).
    ``static_root`` must already be resolved (absolute, symlinks collapsed).
    """
    index = static_root / "index.html"
    try:
        candidate = (static_root / full_path).resolve()
    except (OSError, RuntimeError):
        return index
    if full_path and candidate.is_file() and static_root in candidate.parents:
        return candidate
    return index


def mount_spa(target: FastAPI, static_dir: Path) -> None:
    """Register a catch-all that serves the built SPA from ``static_dir``.

    Unknown ``/api/*`` paths return 404 rather than falling through to the SPA,
    so API misses keep proper HTTP semantics; everything else falls back to
    ``index.html`` for client-side routing. Mount this AFTER the API routers so
    real API routes match first.
    """
    static_root = static_dir.resolve()

    @target.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(_safe_static_path(full_path, static_root))


# Serve the built SPA when a static dir is present (production single-image deploy).
# Absent in dev/test, so this block is skipped there and the API tests are unaffected.
_STATIC_DIR = Path(os.getenv("SPROUT_STATIC_DIR", "static"))

if _STATIC_DIR.is_dir():
    mount_spa(app, _STATIC_DIR)
