"""REST API routes for auth, exams, grading, student history, summary, rankings, and statistics."""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from comlicense_grader.auth import (
    build_session_expiry,
    clear_session_cookie,
    generate_session_token,
    get_optional_student,
    hash_password,
    hash_session_token,
    require_authenticated_student,
    set_session_cookie,
    verify_password,
)
from comlicense_grader.config import (
    ALLOWED_EXTENSIONS,
    MAX_SCORES,
    MAX_UPLOAD_SIZE_BYTES,
    SESSION_COOKIE_NAME,
)
from comlicense_grader.db.common import (
    DuplicateLoginIdError,
    RepositoryConnectionError,
    build_student_history_summary,
)
from comlicense_grader.db.repository import get_repository
from comlicense_grader.grader.engine import get_engine
from comlicense_grader.models.schemas import (
    AuthResponse,
    ExamListResponse,
    GradeResponse,
    LoginRequest,
    RankingsResponse,
    RegisterRequest,
    SectionScores,
    StatisticsResponse,
    StudentSubmissionsResponse,
    SummaryStats,
)

router = APIRouter(prefix="/api", tags=["comlicense"])


# ---------- Auth Routes ----------


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
async def register_student(payload: RegisterRequest, response: Response) -> AuthResponse:
    """Register a non-PII student account and immediately create a login session."""
    repo = get_repository()
    pw_hash = hash_password(payload.password)
    try:
        student = repo.create_student(
            login_id=payload.login_id,
            password_hash=pw_hash,
            display_nickname=payload.display_nickname,
            default_teacher_code=payload.default_teacher_code,
        )
        raw_token, token_hash = generate_session_token()
        _, expires_iso = build_session_expiry()
        repo.create_session(student.id, token_hash, expires_iso)
    except DuplicateLoginIdError as exc:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.") from exc
    except RepositoryConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    set_session_cookie(response, raw_token)
    return AuthResponse(authenticated=True, student=student)


@router.post("/auth/login", response_model=AuthResponse)
async def login_student(payload: LoginRequest, response: Response) -> AuthResponse:
    """Authenticate an existing student account and issue an HttpOnly session cookie."""
    repo = get_repository()
    try:
        found = repo.get_student_by_login_id(payload.login_id)
    except RepositoryConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if found is None:
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    student, stored_hash = found
    if student.status != "active":
        raise HTTPException(
            status_code=403,
            detail="사용이 제한되었거나 탈퇴한 계정입니다.",
        )
    if not verify_password(payload.password, stored_hash):
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    raw_token, token_hash = generate_session_token()
    _, expires_iso = build_session_expiry()
    try:
        repo.create_session(student.id, token_hash, expires_iso)
        repo.update_last_login(student.id)
    except RepositoryConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    set_session_cookie(response, raw_token)
    return AuthResponse(authenticated=True, student=student)


@router.post("/auth/logout", response_model=AuthResponse)
async def logout_student(request: Request, response: Response) -> AuthResponse:
    """Invalidate the active session cookie and remove its hash from storage."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if raw_token:
        repo = get_repository()
        try:
            repo.delete_session(hash_session_token(raw_token))
        except RepositoryConnectionError:
            pass
    clear_session_cookie(response)
    return AuthResponse(authenticated=False, student=None)


@router.get("/auth/me", response_model=AuthResponse)
async def get_current_student(request: Request) -> AuthResponse:
    """Return the currently authenticated student profile, or authenticated=false."""
    repo = get_repository()
    try:
        student = get_optional_student(request, repo)
    except RepositoryConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if student is None:
        return AuthResponse(authenticated=False, student=None)
    return AuthResponse(authenticated=True, student=student)


# ---------- Student History Routes ----------


@router.get("/my/submissions", response_model=StudentSubmissionsResponse)
async def get_my_submissions(
    request: Request,
    exam_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> StudentSubmissionsResponse:
    """Return grading history and progress summary for the logged-in student."""
    repo = get_repository()
    try:
        student = require_authenticated_student(request, repo)
        exam_filter = exam_id.strip() if exam_id and exam_id.strip() else None
        items = repo.get_student_submissions(
            student_id=student.id,
            exam_id=exam_filter,
            limit=limit,
        )
    except RepositoryConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    exam_titles = {e.exam_id: e.title for e in get_engine().load_catalog()}
    for item in items:
        item.exam_title = exam_titles.get(item.exam_id, item.exam_id)

    summary = build_student_history_summary(items)
    return StudentSubmissionsResponse(
        student=student,
        summary=summary,
        submissions=items,
    )


# ---------- Exam & Grading Routes ----------


@router.get("/exams", response_model=ExamListResponse)
async def list_exams() -> ExamListResponse:
    """Return the list of available exam rounds from catalog.json."""
    engine = get_engine()
    return ExamListResponse(exams=engine.load_catalog())


@router.get("/exams/download-all")
async def download_all_exams() -> StreamingResponse:
    """Bundle all catalog exam question workbooks and problem sheets into a single ZIP download."""
    engine = get_engine()
    exams = engine.load_catalog()
    if not exams:
        raise HTTPException(status_code=404, detail="등록된 모의고사 파일이 없습니다.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for exam in exams:
            try:
                _, q_path, _ = engine.resolve_exam_files(exam.exam_id)
            except (ValueError, FileNotFoundError):
                continue
            safe_title = exam.title.replace("/", "_").replace(" ", "_")
            zf.write(q_path, arcname=f"{exam.exam_id}_{safe_title}_실습파일{q_path.suffix}")
            _, sheet_path = engine.resolve_problem_sheet(exam.exam_id)
            if sheet_path is not None:
                zf.write(sheet_path, arcname=f"{exam.exam_id}_{safe_title}_문제지{sheet_path.suffix}")

    buf.seek(0)
    headers = {
        "Content-Disposition": "attachment; filename*=UTF-8''comlicense_exams_all.zip"
    }
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


@router.get("/exams/{exam_id}/problem-sheet")
async def view_problem_sheet(exam_id: str) -> FileResponse:
    """Serve the printable HTML problem sheet for the selected exam round."""
    engine = get_engine()
    try:
        _, sheet_path = engine.resolve_problem_sheet(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if sheet_path is None:
        raise HTTPException(status_code=404, detail="해당 회차의 문제지가 아직 등록되지 않았습니다.")

    return FileResponse(path=sheet_path, media_type="text/html; charset=utf-8")


@router.get("/exams/{exam_id}/download")
async def download_exam(exam_id: str, raw: bool = Query(False)) -> Response:
    """Download the exam bundle (problem sheet + .xlsm workbook) as ZIP, or raw .xlsm when raw=true."""
    engine = get_engine()
    try:
        exam, q_path, _ = engine.resolve_exam_files(exam_id)
        _, sheet_path = engine.resolve_problem_sheet(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if raw or sheet_path is None:
        download_name = f"{exam.title}_실습파일{q_path.suffix}"
        encoded_name = quote(download_name)
        return FileResponse(
            path=q_path,
            media_type="application/vnd.ms-excel.sheet.macroEnabled.12",
            headers={
                "Content-Disposition": f"attachment; filename=\"question{q_path.suffix}\"; filename*=UTF-8''{encoded_name}"
            },
        )

    safe_title = exam.title.replace("/", "_").replace(" ", "_")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(sheet_path, arcname=f"{safe_title}_문제지{sheet_path.suffix}")
        zf.write(q_path, arcname=f"{safe_title}_실습파일{q_path.suffix}")
    buf.seek(0)
    encoded_zip = quote(f"{safe_title}_문제및실습파일.zip")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{exam.exam_id}.zip\"; filename*=UTF-8''{encoded_zip}"
        },
    )


@router.post("/grade", response_model=GradeResponse)
async def grade_submission(
    request: Request,
    exam_id: str = Form("sample_01"),
    teacher_id: str = Form(""),
    student_nickname: str = Form(""),
    file: UploadFile = File(...),
) -> GradeResponse:
    """Accept an uploaded .xlsx/.xlsm workbook, grade it, save to storage, and return details."""
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 파일 형식입니다. .xlsx 또는 .xlsm 파일만 업로드해 주세요.",
        )

    content = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일은 채점할 수 없습니다.")
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="파일 크기가 제한(20MB)을 초과했습니다.",
        )

    engine = get_engine()
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        scores, deductions, exam, pass_threshold = engine.grade_file(exam_id, tmp_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    passed = scores.total >= pass_threshold
    repo = get_repository()
    try:
        current_student = get_optional_student(request, repo)
        resolved_student_id = current_student.id if current_student else None
        resolved_nickname = (
            student_nickname.strip()
            or (current_student.display_nickname if current_student else "익명")
        )
        resolved_teacher = (
            teacher_id.strip()
            or (current_student.default_teacher_code if current_student else "")
        )

        submission_id, graded_at = repo.save_submission(
            exam_id=exam.exam_id,
            teacher_id=resolved_teacher,
            student_nickname=resolved_nickname,
            scores=scores,
            passed=passed,
            deductions=deductions,
            student_id=resolved_student_id,
            file_ext=ext,
        )
        summary = repo.get_summary(exam.exam_id)
    except RepositoryConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return GradeResponse(
        submission_id=submission_id,
        student_id=resolved_student_id,
        exam_id=exam.exam_id,
        exam_title=exam.title,
        teacher_id=resolved_teacher,
        student_nickname=resolved_nickname,
        scores=scores,
        max_scores=SectionScores(**MAX_SCORES),
        passed=passed,
        pass_threshold=pass_threshold,
        deductions=deductions,
        summary=summary,
        graded_at=graded_at,
    )


@router.get("/summary", response_model=SummaryStats)
async def get_summary(exam_id: str = Query("sample_01")) -> SummaryStats:
    """Return participant count and average score for an exam round."""
    engine = get_engine()
    try:
        engine.get_exam(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        return get_repository().get_summary(exam_id)
    except RepositoryConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/rankings", response_model=RankingsResponse)
async def get_rankings(exam_id: str = Query("sample_01")) -> RankingsResponse:
    """Return masked top 10 students and top 5 teachers for an exam round."""
    engine = get_engine()
    try:
        engine.get_exam(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        students, teachers = get_repository().get_rankings(exam_id)
    except RepositoryConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return RankingsResponse(exam_id=exam_id, students=students, teachers=teachers)


@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics(
    request: Request,
    exam_id: str = Query("sample_01"),
    my: int | None = Query(None, ge=0, le=100),
    jum0: int | None = Query(None, ge=0, le=20),
    jum1: int | None = Query(None, ge=0, le=40),
    jum2: int | None = Query(None, ge=0, le=20),
    jum3: int | None = Query(None, ge=0, le=20),
) -> StatisticsResponse:
    """Return score distribution charts for total and 4 section scores."""
    engine = get_engine()
    try:
        exam = engine.get_exam(exam_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    repo = get_repository()
    my_scores: SectionScores | None = None
    if any(v is not None for v in (my, jum0, jum1, jum2, jum3)):
        p1 = jum0 if jum0 is not None else 0
        p2 = jum1 if jum1 is not None else 0
        p3 = jum2 if jum2 is not None else 0
        p4 = jum3 if jum3 is not None else 0
        total = my if my is not None else min(100, p1 + p2 + p3 + p4)
        my_scores = SectionScores(
            problem1=p1,
            problem2=p2,
            problem3=p3,
            problem4=p4,
            total=total,
        )
    else:
        try:
            current_student = get_optional_student(request, repo)
            if current_student is not None:
                my_scores = repo.get_student_latest_scores(current_student.id, exam_id)
        except RepositoryConnectionError:
            pass

    try:
        count, avg_score, charts = repo.get_statistics(exam_id, my_scores=my_scores)
    except RepositoryConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return StatisticsResponse(
        exam_id=exam.exam_id,
        exam_title=exam.title,
        participant_count=count,
        average_score=avg_score,
        my_scores=my_scores,
        charts=charts,
    )
