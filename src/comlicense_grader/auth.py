"""Password hashing and stateless-token-hashed cookie session helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from comlicense_grader.config import (
    SESSION_COOKIE_NAME,
    get_session_ttl_hours,
    is_cookie_secure,
)
from comlicense_grader.models.schemas import StudentProfile

KST = timezone(timedelta(hours=9))
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def hash_password(password: str) -> str:
    """Hash a plaintext password using salted scrypt."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored scrypt hash in constant time."""
    try:
        scheme, n_str, r_str, p_str, salt_hex, hash_hex = stored_hash.split("$", 5)
        if scheme != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n_str),
            r=int(r_str),
            p=int(p_str),
            dklen=len(bytes.fromhex(hash_hex)),
        )
        return hmac.compare_digest(derived, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


def generate_session_token() -> tuple[str, str]:
    """Return (raw_cookie_token, sha256_token_hash)."""
    raw = secrets.token_urlsafe(32)
    token_hash = hash_session_token(raw)
    return raw, token_hash


def hash_session_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest stored in user_sessions.token_hash."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def build_session_expiry() -> tuple[datetime, str]:
    """Return (expiry_dt_utc, kst_or_iso_timestamp)."""
    expires_dt = datetime.now(tz=timezone.utc) + timedelta(hours=get_session_ttl_hours())
    return expires_dt, expires_dt.isoformat()


def set_session_cookie(response: Response, raw_token: str) -> None:
    """Attach the HttpOnly session cookie to the response."""
    max_age = get_session_ttl_hours() * 3600
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=is_cookie_secure(),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Remove the session cookie from the client."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=is_cookie_secure(),
        path="/",
    )


def get_optional_student(request: Request, repo: object) -> StudentProfile | None:
    """Resolve the currently authenticated student from the session cookie, if valid."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        return None
    token_hash = hash_session_token(raw_token)
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    return repo.get_student_by_session_token(token_hash, now_iso)  # type: ignore[attr-defined]


def require_authenticated_student(request: Request, repo: object) -> StudentProfile:
    """Return the authenticated student or raise HTTP 401."""
    student = get_optional_student(request, repo)
    if student is None:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다. 학생 계정으로 로그인한 뒤 다시 시도해 주세요.",
        )
    return student
