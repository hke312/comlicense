"""Vercel Serverless Function entrypoint exposing the FastAPI app."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from comlicense_grader.main import app  # noqa: E402, F401
