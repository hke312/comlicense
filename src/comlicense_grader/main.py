"""FastAPI application entry point unifying all pages and grading APIs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from comlicense_grader.api.routes import router as api_router
from comlicense_grader.config import (
    STATIC_DIR,
    get_storage_backend,
    get_supabase_service_role_key,
    get_supabase_url,
)
from comlicense_grader.db.repository import get_repository
from comlicense_grader.grader.engine import get_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize repository backend and grading engine on startup."""
    get_repository()
    get_engine()
    yield


app = FastAPI(
    title="컴퓨터활용능력 2급 실기 채점 프로그램",
    description="대한상공회의소 컴퓨터활용능력 2급 실기 시험 자동 채점 및 통계 플랫폼",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def page_home() -> FileResponse:
    """Serve the main grading page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/history", include_in_schema=False)
async def page_history() -> FileResponse:
    """Serve the authenticated student's grading history page."""
    return FileResponse(STATIC_DIR / "history.html")


@app.get("/statistics", include_in_schema=False)
async def page_statistics() -> FileResponse:
    """Serve the score distribution & problem ratio statistics page."""
    return FileResponse(STATIC_DIR / "statistics.html")


@app.get("/criteria", include_in_schema=False)
@app.get("/help", include_in_schema=False)
async def page_criteria() -> FileResponse:
    """Serve the grading criteria and help page."""
    return FileResponse(STATIC_DIR / "criteria.html")


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, object]:
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "backend": get_storage_backend(),
        "supabase_url_set": bool(get_supabase_url()),
        "supabase_service_key_set": bool(get_supabase_service_role_key()),
    }
