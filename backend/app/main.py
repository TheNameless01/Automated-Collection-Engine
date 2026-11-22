"""FastAPI application entry point for DZ Car Rental Finder."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Ensure backend/ is importable regardless of cwd
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.routes import router as api_router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.database.connection import db_manager
from app.database.migrations import run_migrations
from app.geography.service import get_geography_service

logger = logging.getLogger("dz_finder")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.logs_dir, settings.db_path, settings.log_level)
    run_migrations(db_manager, settings.boundaries_dir)
    get_geography_service()
    logger.info("DZ Car Rental Finder backend initialized (69-wilaya dataset ready)")
    yield
    logger.info("DZ Car Rental Finder backend shutting down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DZ Car Rental Finder API",
        version="1.0.0",
        description="Local-first car rental agency discovery across all 69 Algerian wilayas.",
        lifespan=lifespan,
    )

    # Strict localhost CORS by default
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    # Serve built frontend SPA when running standalone (Windows desktop launcher / production)
    dist_dir = settings.dist_dir
    if dist_dir.exists() and (dist_dir / "index.html").exists():
        assets_dir = dist_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str) -> FileResponse:
            candidate = (dist_dir / full_path).resolve()
            if full_path and candidate.is_file() and str(candidate).startswith(str(dist_dir)):
                return FileResponse(str(candidate))
            return FileResponse(str(dist_dir / "index.html"))

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
