"""
Public Narrative & Governance Signal Monitor
Main FastAPI application.
"""

import os
import sys
import pathlib

# ──────────────────────────────────────────────────────────────
# PATH SETUP — must happen before any local imports
# Guarantees that 'models', 'routers', 'services' are importable
# regardless of where gunicorn/uvicorn launches from.
# ──────────────────────────────────────────────────────────────

# Strategy 1: Use this file's location
_this_file = pathlib.Path(__file__).resolve()
_app_dir = str(_this_file.parent)

# Strategy 2: Known Render path
_render_dir = "/opt/render/project/src"

# Strategy 3: Look for models/ directory to confirm we have the right path
def _find_app_root():
    """Find the directory containing models/ routers/ services/"""
    candidates = [
        _app_dir,
        _render_dir,
        os.getcwd(),
        str(pathlib.Path.cwd()),
    ]
    for path in candidates:
        if os.path.isdir(os.path.join(path, "models")):
            return path
    return _app_dir  # fallback

_root = _find_app_root()

# Apply: set working directory and ensure it's on sys.path
os.chdir(_root)
if _root not in sys.path:
    sys.path.insert(0, _root)

# Debug output (visible in Render logs)
print(f"[PNGSM] __file__     = {__file__}", flush=True)
print(f"[PNGSM] _app_dir     = {_app_dir}", flush=True)
print(f"[PNGSM] _root        = {_root}", flush=True)
print(f"[PNGSM] cwd          = {os.getcwd()}", flush=True)
print(f"[PNGSM] sys.path[:5] = {sys.path[:5]}", flush=True)
print(f"[PNGSM] models/ exists at root = {os.path.isdir(os.path.join(_root, 'models'))}", flush=True)
print(f"[PNGSM] ls root = {os.listdir(_root)}", flush=True)

# ──────────────────────────────────────────────────────────────
# Now safe to import local modules
# ──────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from models.database import init_db
from routers import companies, ingestion, analysis


@asynccontextmanager
async def lifespan(app: FastAPI):
    report_dir = os.environ.get(
        "PNGSM_REPORT_DIR",
        os.path.join(_root, "data", "reports")
    )
    os.makedirs(report_dir, exist_ok=True)
    await init_db()
    yield


app = FastAPI(
    title="Public Narrative & Governance Signal Monitor",
    description="Continuously evaluate the external environment around a client using public data, detect pressure accumulation, and translate into advisory implications.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(companies.router)
app.include_router(ingestion.router)
app.include_router(analysis.router)

static_dir = os.path.join(_root, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "PNGSM API", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
