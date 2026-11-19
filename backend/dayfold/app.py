"""FastAPI application: API, device feed, fonts and the built dashboard."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, auth, editions, kindle, providers, readers
from .bootstrap import bootstrap
from .config import FONTS_DIR, config
from .i18n import tr
from .jobs.queue import recover_interrupted, start_worker, stop_worker
from .jobs.scheduler import start_scheduler, stop_scheduler

log = logging.getLogger("dayfold")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap()
    recover_interrupted()
    start_worker()
    if not config.disable_scheduler:
        start_scheduler()
    log.info("Dayfold pronto em http://%s:%s (dados em %s)", config.host, config.port, config.data_dir)
    yield
    stop_scheduler()
    stop_worker()


app = FastAPI(title="Dayfold", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(providers.router)
app.include_router(editions.router)
app.include_router(editions.feed)
app.include_router(readers.router)
app.include_router(kindle.router)
app.include_router(kindle.feed)
app.mount("/fonts", StaticFiles(directory=FONTS_DIR), name="fonts")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.exception_handler(HTTPException)
async def http_error(_request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


def _spa_index() -> Path | None:
    index = config.web_dir / "index.html"
    return index if index.exists() else None


if (config.web_dir / "assets").exists():
    app.mount("/assets", StaticFiles(directory=config.web_dir / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith(("api/", "feed/", "opds")):
        raise HTTPException(404, tr("não encontrado", "not found"))
    candidate = (config.web_dir / path).resolve()
    if path and candidate.is_file() and config.web_dir.resolve() in candidate.parents:
        return FileResponse(candidate)
    index = _spa_index()
    if index is None:
        return JSONResponse({"detail": tr("dashboard não compilado: rode `make build` (frontend)",
                                         "dashboard not built: run `make build` (frontend)")}, status_code=503)
    return FileResponse(index)
