import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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


# Serve the built SPA when a static dir is present (production single-image deploy).
# Absent in dev/test, so this block is skipped there and the API tests are unaffected.
_STATIC_DIR = Path(os.getenv("SPROUT_STATIC_DIR", "static"))

if _STATIC_DIR.is_dir():
    _STATIC_ROOT = _STATIC_DIR.resolve()

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        return FileResponse(_safe_static_path(full_path, _STATIC_ROOT))
