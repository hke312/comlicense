"""Supabase PostgREST-backed repository for students, sessions, submissions, and analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from comlicense_grader.db.common import (
    DuplicateLoginIdError,
    RepositoryConnectionError,
    aggregate_teacher_rankings,
    build_statistics_charts,
    build_student_ranking_items,
    format_kst_timestamp,
    parse_deductions,
)
from comlicense_grader.models.schemas import (
    ChartSeries,
    DeductionItem,
    SectionScores,
    StudentRankingItem,
    StudentProfile,
    StudentSubmissionItem,
    SummaryStats,
    TeacherRankingItem,
)


class SupabaseRepository:
    """Supabase REST API storage for student accounts, sessions, and graded submissions."""

    def __init__(self, supabase_url: str, service_role_key: str) -> None:
        self.supabase_url = supabase_url.rstrip("/")
        self.rest_url = f"{self.supabase_url}/rest/v1"
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }
        self._client = httpx.Client(
            base_url=self.rest_url,
            headers=self.headers,
            timeout=15.0,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | list[tuple[str, str]] | None = None,
        json_body: Any = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = dict(self.headers)
        if extra_headers:
            headers.update(extra_headers)
        try:
            resp = self._client.request(
                method,
                path,
                params=params,
                json=json_body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise RepositoryConnectionError(f"Supabase 연결 오류: {exc}") from exc

        if resp.status_code == 409:
            raise DuplicateLoginIdError("이미 사용 중인 아이디입니다.")
        if resp.status_code >= 400:
            raise RepositoryConnectionError(
                f"Supabase 요청 실패 (HTTP {resp.status_code}): {resp.text}"
            )
        return resp

    def _select_paginated(
        self,
        table: str,
        params: dict[str, str],
        page_size: int = 1000,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            resp = self._request(
                "GET",
                f"/{table}",
                params=params,
                extra_headers={"Range": f"{offset}-{offset + page_size - 1}"},
            )
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return rows

    @staticmethod
    def _row_to_student(row: dict[str, Any]) -> StudentProfile:
        return StudentProfile(
            id=int(row["id"]),
            login_id=str(row["login_id"]),
            display_nickname=str(row["display_nickname"]),
            default_teacher_code=str(row.get("default_teacher_code") or ""),
            status=str(row.get("status") or "active"),
            created_at=format_kst_timestamp(row.get("created_at")),
            last_login_at=format_kst_timestamp(row.get("last_login_at"))
            if row.get("last_login_at")
            else None,
        )

    # ---------- Student Auth & Sessions ----------

    def create_student(
        self,
        login_id: str,
        password_hash: str,
        display_nickname: str,
        default_teacher_code: str = "",
    ) -> StudentProfile:
        resp = self._request(
            "POST",
            "/students",
            json_body={
                "login_id": login_id.strip(),
                "password_hash": password_hash,
                "display_nickname": display_nickname.strip(),
                "default_teacher_code": default_teacher_code.strip(),
                "status": "active",
            },
            extra_headers={"Prefer": "return=representation"},
        )
        rows = resp.json()
        if not rows:
            raise RepositoryConnectionError("학생 계정 생성 결과를 확인할 수 없습니다.")
        return self._row_to_student(rows[0])

    def get_student_by_login_id(
        self, login_id: str
    ) -> tuple[StudentProfile, str] | None:
        resp = self._request(
            "GET",
            "/students",
            params={
                "login_id": f"eq.{login_id.strip()}",
                "select": "id,login_id,password_hash,display_nickname,default_teacher_code,status,created_at,last_login_at",
                "limit": "1",
            },
        )
        rows = resp.json()
        if not rows:
            return None
        row = rows[0]
        return self._row_to_student(row), str(row["password_hash"])

    def get_student_by_id(self, student_id: int) -> StudentProfile | None:
        resp = self._request(
            "GET",
            "/students",
            params={
                "id": f"eq.{student_id}",
                "select": "id,login_id,display_nickname,default_teacher_code,status,created_at,last_login_at",
                "limit": "1",
            },
        )
        rows = resp.json()
        return self._row_to_student(rows[0]) if rows else None

    def update_last_login(self, student_id: int) -> None:
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        self._request(
            "PATCH",
            "/students",
            params={"id": f"eq.{student_id}"},
            json_body={"last_login_at": now_iso},
            extra_headers={"Prefer": "return=minimal"},
        )

    def create_session(self, student_id: int, token_hash: str, expires_at: str) -> None:
        self._request(
            "POST",
            "/user_sessions",
            json_body={
                "student_id": student_id,
                "token_hash": token_hash,
                "expires_at": expires_at,
            },
            extra_headers={"Prefer": "return=minimal"},
        )

    def get_student_by_session_token(
        self, token_hash: str, now_iso: str
    ) -> StudentProfile | None:
        resp = self._request(
            "GET",
            "/user_sessions",
            params={
                "token_hash": f"eq.{token_hash}",
                "expires_at": f"gt.{now_iso}",
                "select": "student_id,students!inner(id,login_id,display_nickname,default_teacher_code,status,created_at,last_login_at)",
                "limit": "1",
            },
        )
        rows = resp.json()
        if not rows:
            return None
        student_data = rows[0].get("students")
        if not isinstance(student_data, dict):
            return None
        if student_data.get("status") != "active":
            return None
        return self._row_to_student(student_data)

    def delete_session(self, token_hash: str) -> None:
        self._request(
            "DELETE",
            "/user_sessions",
            params={"token_hash": f"eq.{token_hash}"},
            extra_headers={"Prefer": "return=minimal"},
        )

    # ---------- Submissions & Analytics ----------

    def save_submission(
        self,
        exam_id: str,
        teacher_id: str,
        student_nickname: str,
        scores: SectionScores,
        passed: bool,
        deductions: list[DeductionItem],
        student_id: int | None = None,
        file_ext: str = "",
        created_at: str | None = None,
    ) -> tuple[int, str]:
        payload: dict[str, Any] = {
            "student_id": student_id,
            "exam_id": exam_id,
            "teacher_id": teacher_id.strip(),
            "student_nickname": student_nickname.strip() or "익명",
            "score_p1": scores.problem1,
            "score_p2": scores.problem2,
            "score_p3": scores.problem3,
            "score_p4": scores.problem4,
            "total_score": scores.total,
            "passed": bool(passed),
            "file_ext": file_ext if file_ext in (".xlsx", ".xlsm") else "",
            "deductions_json": [d.model_dump() for d in deductions],
        }
        if created_at:
            payload["created_at"] = created_at

        resp = self._request(
            "POST",
            "/submissions",
            json_body=payload,
            extra_headers={"Prefer": "return=representation"},
        )
        rows = resp.json()
        if not rows:
            raise RepositoryConnectionError("채점 결과 저장 응답이 비어 있습니다.")

        sub_row = rows[0]
        submission_id = int(sub_row["id"])
        graded_at = format_kst_timestamp(sub_row.get("created_at"))

        if deductions:
            deduction_rows = [
                {
                    "submission_id": submission_id,
                    "problem_no": d.problem_no,
                    "task_name": d.task_name,
                    "deduction": d.deduction,
                    "detail": d.detail,
                }
                for d in deductions
            ]
            self._request(
                "POST",
                "/submission_deductions",
                json_body=deduction_rows,
                extra_headers={"Prefer": "return=minimal"},
            )

        return submission_id, graded_at

    def get_summary(self, exam_id: str) -> SummaryStats:
        rows = self._select_paginated(
            "submissions",
            {"exam_id": f"eq.{exam_id}", "select": "total_score"},
        )
        count = len(rows)
        avg = (
            round(sum(int(r["total_score"]) for r in rows) / count, 2)
            if count > 0
            else 0.0
        )
        return SummaryStats(
            exam_id=exam_id,
            participant_count=count,
            average_score=avg,
            waiting_count=0,
        )

    def get_rankings(
        self,
        exam_id: str,
        student_limit: int = 10,
        teacher_limit: int = 5,
    ) -> tuple[list[StudentRankingItem], list[TeacherRankingItem]]:
        student_resp = self._request(
            "GET",
            "/submissions",
            params={
                "exam_id": f"eq.{exam_id}",
                "select": "student_nickname,total_score,created_at",
                "order": "total_score.desc,id.asc",
                "limit": str(student_limit),
            },
        )
        student_rows = student_resp.json()
        students = build_student_ranking_items(student_rows)

        teacher_rows = self._select_paginated(
            "submissions",
            {
                "exam_id": f"eq.{exam_id}",
                "teacher_id": "neq.",
                "select": "teacher_id,total_score",
            },
        )
        teachers = aggregate_teacher_rankings(teacher_rows, teacher_limit=teacher_limit)
        return students, teachers

    def get_statistics(
        self,
        exam_id: str,
        my_scores: SectionScores | None = None,
    ) -> tuple[int, float, dict[str, ChartSeries]]:
        rows = self._select_paginated(
            "submissions",
            {
                "exam_id": f"eq.{exam_id}",
                "select": "score_p1,score_p2,score_p3,score_p4,total_score",
            },
        )
        return build_statistics_charts(rows, my_scores=my_scores)

    def get_student_submissions(
        self,
        student_id: int,
        exam_id: str | None = None,
        limit: int = 50,
    ) -> list[StudentSubmissionItem]:
        params: dict[str, str] = {
            "student_id": f"eq.{student_id}",
            "select": "id,exam_id,teacher_id,student_nickname,score_p1,score_p2,score_p3,score_p4,total_score,passed,file_ext,deductions_json,created_at",
            "order": "created_at.desc,id.desc",
            "limit": str(limit),
        }
        if exam_id:
            params["exam_id"] = f"eq.{exam_id}"

        resp = self._request("GET", "/submissions", params=params)
        rows = resp.json()
        return [
            StudentSubmissionItem(
                id=int(r["id"]),
                exam_id=str(r["exam_id"]),
                teacher_id=str(r.get("teacher_id") or ""),
                student_nickname=str(r.get("student_nickname") or "익명"),
                scores=SectionScores(
                    problem1=int(r["score_p1"]),
                    problem2=int(r["score_p2"]),
                    problem3=int(r["score_p3"]),
                    problem4=int(r["score_p4"]),
                    total=int(r["total_score"]),
                ),
                passed=bool(r["passed"]),
                file_ext=str(r.get("file_ext") or ""),
                deductions=parse_deductions(r.get("deductions_json")),
                created_at=format_kst_timestamp(r.get("created_at")),
            )
            for r in rows
        ]

    def get_student_latest_scores(
        self, student_id: int, exam_id: str
    ) -> SectionScores | None:
        resp = self._request(
            "GET",
            "/submissions",
            params={
                "student_id": f"eq.{student_id}",
                "exam_id": f"eq.{exam_id}",
                "select": "score_p1,score_p2,score_p3,score_p4,total_score",
                "order": "created_at.desc,id.desc",
                "limit": "1",
            },
        )
        rows = resp.json()
        if not rows:
            return None
        r = rows[0]
        return SectionScores(
            problem1=int(r["score_p1"]),
            problem2=int(r["score_p2"]),
            problem3=int(r["score_p3"]),
            problem4=int(r["score_p4"]),
            total=int(r["total_score"]),
        )
