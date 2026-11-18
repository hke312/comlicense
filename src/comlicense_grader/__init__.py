"""컴퓨터활용능력 2급 실기 채점 프로그램 패키지."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Run the FastAPI server using uvicorn."""
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "comlicense_grader.main:app",
        host=host,
        port=port,
        reload=False,
    )
