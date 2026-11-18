"""Application configuration and constants for comlicense_grader."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

BASE_DIR: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = BASE_DIR / "data"
EXAMS_DIR: Path = DATA_DIR / "exams"
CATALOG_PATH: Path = EXAMS_DIR / "catalog.json"
STATIC_DIR: Path = BASE_DIR / "static"


def _load_dotenv_if_present() -> None:
    """Populate unset environment variables from a local .env file if present."""
    env_path = BASE_DIR / ".env"
    if not env_path.is_file():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


_load_dotenv_if_present()


def get_db_path() -> Path:
    """Return the configured SQLite database file path."""
    override = os.getenv("COMLICENSE_DB_PATH")
    if override:
        return Path(override)
    return DATA_DIR / "comlicense.db"


def get_supabase_url() -> str:
    """Return the configured Supabase project URL, or empty string if unset."""
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def get_supabase_service_role_key() -> str:
    """Return the configured Supabase service_role key, or empty string if unset."""
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def get_storage_backend() -> Literal["supabase", "sqlite"]:
    """Select the active storage backend based on environment configuration."""
    if os.getenv("COMLICENSE_DB_PATH"):
        return "sqlite"
    explicit = os.getenv("COMLICENSE_STORAGE_BACKEND", "").strip().lower()
    if explicit in ("sqlite", "supabase"):
        return explicit  # type: ignore[return-value]
    if get_supabase_url() and get_supabase_service_role_key():
        return "supabase"
    return "sqlite"


def get_session_ttl_hours() -> int:
    """Return session expiration duration in hours."""
    raw = os.getenv("COMLICENSE_SESSION_TTL_HOURS", "168").strip()
    try:
        hours = int(raw)
        return max(1, min(hours, 24 * 90))
    except ValueError:
        return 168


def is_cookie_secure() -> bool:
    """Return whether session cookies should set the Secure attribute."""
    return os.getenv("COMLICENSE_COOKIE_SECURE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )


SESSION_COOKIE_NAME: str = "comlicense_session"
MAX_UPLOAD_SIZE_BYTES: int = 4 * 1024 * 1024  # 4 MB (Vercel payload limit safe)
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".xlsx", ".xlsm"})

PASS_THRESHOLD: int = 70
MAX_SCORES: dict[str, int] = {
    "problem1": 20,
    "problem2": 40,
    "problem3": 20,
    "problem4": 20,
    "total": 100,
}

SECTION_LABELS: dict[str, str] = {
    "total": "총점",
    "problem1": "문제 1 (기본작업)",
    "problem2": "문제 2 (계산작업)",
    "problem3": "문제 3 (분석작업)",
    "problem4": "문제 4 (기타작업)",
}
