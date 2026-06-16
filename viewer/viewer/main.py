from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from viewer.routes import content, jobs, sessions, upload, workspaces

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="doc-chunk-viewer")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(upload.router, prefix="/api")
    app.include_router(workspaces.router, prefix="/api")
    app.include_router(content.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
