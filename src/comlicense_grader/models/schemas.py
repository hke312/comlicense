"""Pydantic v2 data models for exam metadata, student auth, grading results, rankings, and statistics."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_LOGIN_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,30}$")
_PHONE_RE = re.compile(r"^(?:010|011|016|017|018|019)[-\s]?\d{3,4}[-\s]?\d{4}$")
_TEACHER_CODE_RE = re.compile(r"^[a-zA-Z0-9_.-]{2,30}$")


def _reject_pii_text(value: str, field_label: str) -> str:
    cleaned = value.strip()
    if "@" in cleaned:
        raise ValueError(f"{field_label}에 이메일 형식을 사용할 수 없습니다.")
    digits_only = re.sub(r"[-\s]", "", cleaned)
    if _PHONE_RE.match(cleaned) or re.match(r"^(010|011|016|017|018|019)\d{7,8}$", digits_only):
        raise ValueError(f"{field_label}에 전화번호를 사용할 수 없습니다.")
    return cleaned


class ExamInfo(BaseModel):
    """Metadata describing an exam round in the catalog."""

    exam_id: str
    title: str
    description: str = ""
    question_file: str
    answer_spec_file: str
    problem_sheet_file: str | None = None
    fallback_exam_id: str | None = None
    is_sample: bool = False
    available: bool = True


class ExamListResponse(BaseModel):
    """Response payload for GET /api/exams."""

    exams: list[ExamInfo]


class StudentProfile(BaseModel):
    """Non-PII public profile of a logged-in student."""

    id: int
    login_id: str
    display_nickname: str
    default_teacher_code: str = ""
    status: str = "active"
    created_at: str
    last_login_at: str | None = None


class RegisterRequest(BaseModel):
    """Request payload for student sign-up (PII excluded)."""

    login_id: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=8, max_length=72)
    display_nickname: str = Field(..., min_length=1, max_length=30)
    default_teacher_code: str = Field(default="", max_length=30)

    @field_validator("login_id")
    @classmethod
    def validate_login_id(cls, value: str) -> str:
        cleaned = _reject_pii_text(value, "아이디")
        if not _LOGIN_ID_RE.match(cleaned):
            raise ValueError("아이디는 3~30자의 영문, 숫자, '_', '.', '-'만 사용할 수 있습니다.")
        return cleaned

    @field_validator("display_nickname")
    @classmethod
    def validate_nickname(cls, value: str) -> str:
        cleaned = _reject_pii_text(value, "닉네임")
        if not cleaned or len(cleaned) > 30:
            raise ValueError("닉네임은 1~30자로 입력해 주세요.")
        return cleaned

    @field_validator("default_teacher_code")
    @classmethod
    def validate_teacher_code(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        cleaned = _reject_pii_text(cleaned, "선생님 코드")
        if not _TEACHER_CODE_RE.match(cleaned):
            raise ValueError("선생님 코드는 2~30자의 영문, 숫자, '_', '.', '-'만 사용할 수 있습니다.")
        return cleaned


class LoginRequest(BaseModel):
    """Request payload for student login."""

    login_id: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=1, max_length=72)

    @field_validator("login_id")
    @classmethod
    def normalize_login_id(cls, value: str) -> str:
        return value.strip()


class AuthResponse(BaseModel):
    """Response payload for authentication state and profile."""

    authenticated: bool
    student: StudentProfile | None = None


class SectionScores(BaseModel):
    """Scores broken down by the four practical exam sections."""

    problem1: int = Field(..., ge=0, le=20, description="기본작업 (최대 20점)")
    problem2: int = Field(..., ge=0, le=40, description="계산작업 (최대 40점)")
    problem3: int = Field(..., ge=0, le=20, description="분석작업 (최대 20점)")
    problem4: int = Field(..., ge=0, le=20, description="기타작업 (최대 20점)")
    total: int = Field(..., ge=0, le=100, description="총점 (최대 100점)")


class DeductionItem(BaseModel):
    """Single deduction item explaining lost points."""

    problem_no: int = Field(..., ge=1, le=4)
    task_name: str
    deduction: int = Field(..., ge=0)
    detail: str


class SummaryStats(BaseModel):
    """Aggregate summary statistics for a specific exam."""

    exam_id: str
    participant_count: int = Field(..., ge=0)
    average_score: float = Field(..., ge=0.0)
    waiting_count: int = Field(default=0, ge=0)


class GradeResponse(BaseModel):
    """Full response returned after grading a submitted workbook."""

    submission_id: int
    student_id: int | None = None
    exam_id: str
    exam_title: str
    teacher_id: str
    student_nickname: str
    scores: SectionScores
    max_scores: SectionScores
    passed: bool
    pass_threshold: int = 70
    deductions: list[DeductionItem]
    summary: SummaryStats
    graded_at: str


class StudentSubmissionItem(BaseModel):
    """Single historical submission record belonging to the authenticated student."""

    id: int
    exam_id: str
    exam_title: str = ""
    teacher_id: str = ""
    student_nickname: str
    scores: SectionScores
    passed: bool
    file_ext: str = ""
    deductions: list[DeductionItem] = Field(default_factory=list)
    created_at: str


class StudentHistorySummary(BaseModel):
    """Aggregate progress metrics for the authenticated student."""

    total_attempts: int = 0
    pass_count: int = 0
    pass_rate: float = 0.0
    best_score: int = 0
    average_score: float = 0.0


class StudentSubmissionsResponse(BaseModel):
    """Response payload for GET /api/my/submissions."""

    student: StudentProfile
    summary: StudentHistorySummary
    submissions: list[StudentSubmissionItem]


class StudentRankingItem(BaseModel):
    """Single student entry in the top rankings list."""

    rank: int
    nickname: str
    masked_nickname: str
    score: int
    created_at: str


class TeacherRankingItem(BaseModel):
    """Single teacher entry in the top teacher rankings list."""

    rank: int
    teacher_id: str
    masked_teacher_id: str
    student_count: int
    average_score: float


class RankingsResponse(BaseModel):
    """Response payload for GET /api/rankings."""

    exam_id: str
    students: list[StudentRankingItem]
    teachers: list[TeacherRankingItem]


class ChartBucket(BaseModel):
    """Single histogram bucket in score distribution statistics."""

    label: str
    count: int
    percent: float
    is_my: bool = False


class ChartSeries(BaseModel):
    """Histogram series for total score or a section score."""

    title: str
    buckets: list[ChartBucket]


class StatisticsResponse(BaseModel):
    """Response payload for GET /api/statistics."""

    exam_id: str
    exam_title: str
    participant_count: int
    average_score: float
    my_scores: SectionScores | None = None
    charts: dict[str, ChartSeries]
