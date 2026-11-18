"""컴퓨터활용능력 2급 실기 채점 프로그램 패키지."""

from __future__ import annotations

import uvicorn


def main() -> None:
    """Run the FastAPI server using uvicorn."""
    uvicorn.run(
        "comlicense_grader.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
