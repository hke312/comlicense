"""SQLite repository and backend selector for storing students, sessions, and submissions."""

from __future__ import annotations

import json
import random
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from comlicense_grader.config import (
    PASS_THRESHOLD,
    get_db_path,
    get_storage_backend,
    get_supabase_service_role_key,
    get_supabase_url,
)
from comlicense_grader.db.common import (
    KST,
    DuplicateLoginIdError,
    build_statistics_charts,
    build_student_ranking_items,
    mask_name,
    parse_deductions,
)
from comlicense_grader.db.supabase_repository import SupabaseRepository
from comlicense_grader.models.schemas import (
    ChartSeries,
    DeductionItem,
    SectionScores,
    StudentProfile,
    StudentRankingItem,
    StudentSubmissionItem,
    SummaryStats,
    TeacherRankingItem,
)


class SubmissionRepository:
    """SQLite-backed storage for student accounts, sessions, and graded submissions."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path: Path = db_path if db_path is not None else get_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._seed_if_empty()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS teachers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teacher_code TEXT NOT NULL UNIQUE,
                    display_label TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    login_id TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_nickname TEXT NOT NULL,
                    default_teacher_code TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    last_login_at TEXT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_sessions_student ON user_sessions(student_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NULL REFERENCES students(id) ON DELETE SET NULL,
                    exam_id TEXT NOT NULL,
                    teacher_id TEXT NOT NULL DEFAULT '',
                    student_nickname TEXT NOT NULL DEFAULT '익명',
                    score_p1 INTEGER NOT NULL,
                    score_p2 INTEGER NOT NULL,
                    score_p3 INTEGER NOT NULL,
                    score_p4 INTEGER NOT NULL,
                    total_score INTEGER NOT NULL,
                    passed INTEGER NOT NULL,
                    file_ext TEXT NOT NULL DEFAULT '',
                    deductions_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                )
                """
            )
            existing_cols = {
                str(r["name"])
                for r in conn.execute("PRAGMA table_info(submissions)").fetchall()
            }
            if "student_id" not in existing_cols:
                conn.execute(
                    "ALTER TABLE submissions ADD COLUMN student_id INTEGER NULL REFERENCES students(id) ON DELETE SET NULL"
                )
            if "file_ext" not in existing_cols:
                conn.execute(
                    "ALTER TABLE submissions ADD COLUMN file_ext TEXT NOT NULL DEFAULT ''"
                )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_submissions_exam_id ON submissions(exam_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_submissions_exam_score ON submissions(exam_id, total_score DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_submissions_student_exam ON submissions(student_id, exam_id, created_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS submission_deductions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
                    problem_no INTEGER NOT NULL,
                    task_name TEXT NOT NULL,
                    deduction INTEGER NOT NULL,
                    detail TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deductions_submission_id ON submission_deductions(submission_id)"
            )

    def _seed_if_empty(self) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM submissions").fetchone()
            if row and int(row["cnt"]) > 0:
                return

            rows_to_insert = self._build_seed_rows()
            conn.executemany(
                """
                INSERT INTO submissions (
                    exam_id, teacher_id, student_nickname,
                    score_p1, score_p2, score_p3, score_p4,
                    total_score, passed, deductions_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )

    def _build_seed_rows(
        self,
    ) -> list[tuple[str, str, str, int, int, int, int, int, int, str, str]]:
        """Generate deterministic baseline submissions (~2,103 for sample_01, avg ~39.01)."""
        rng = random.Random(20260418)
        base_dt = datetime(2026, 4, 1, 9, 0, 0, tzinfo=KST)
        rows: list[tuple[str, str, str, int, int, int, int, int, int, str, str]] = []

        top_students = [
            ("오민석", "teacher01", 20, 40, 20, 20),
            ("김서연", "teacher01", 20, 40, 20, 18),
            ("이도현", "park_edu", 20, 40, 20, 16),
            ("박지우", "teacher01", 20, 40, 20, 15),
            ("최하윤", "kim_lab", 18, 40, 20, 16),
            ("정우진", "park_edu", 20, 32, 20, 20),
            ("강수빈", "teacher01", 20, 40, 10, 20),
            ("조예준", "lee_pro", 18, 40, 20, 12),
            ("윤채원", "kim_lab", 20, 32, 20, 16),
            ("한지훈", "choi_it", 18, 32, 20, 16),
        ]
        for idx, (nick, tid, p1, p2, p3, p4) in enumerate(top_students):
            total = p1 + p2 + p3 + p4
            ts = (base_dt + timedelta(hours=idx * 3 + 1)).strftime("%Y-%m-%d %H:%M:%S")
            rows.append(("sample_01", tid, nick, p1, p2, p3, p4, total, int(total >= PASS_THRESHOLD), "[]", ts))

        teacher_pool = [
            ("teacher01", 0.14),
            ("park_edu", 0.10),
            ("kim_lab", 0.08),
            ("lee_pro", 0.07),
            ("choi_it", 0.06),
            ("", 0.55),
        ]
        teacher_names = [t[0] for t in teacher_pool]
        teacher_weights = [t[1] for t in teacher_pool]

        p1_choices = [0, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 18, 20]
        p1_weights = [6, 5, 6, 7, 8, 6, 9, 6, 11, 6, 9, 7, 5, 4, 3, 2]

        p2_choices = [0, 8, 16, 24, 32, 40]
        p2_weights = [28, 30, 22, 12, 6, 2]

        p3_choices = [0, 10, 20]
        p3_weights = [48, 36, 16]

        p4_choices = [0, 2, 4, 5, 6, 8, 10, 12, 14, 15, 16, 18, 20]
        p4_weights = [10, 8, 9, 8, 8, 10, 12, 10, 8, 5, 5, 4, 3]

        first_chars = "김이박최정강조윤장임한오서신권황안송류홍"
        remaining_sample = 2103 - len(top_students)
        for i in range(remaining_sample):
            tid = rng.choices(teacher_names, weights=teacher_weights, k=1)[0]
            p1 = rng.choices(p1_choices, weights=p1_weights, k=1)[0]
            p2 = rng.choices(p2_choices, weights=p2_weights, k=1)[0]
            p3 = rng.choices(p3_choices, weights=p3_weights, k=1)[0]
            p4 = rng.choices(p4_choices, weights=p4_weights, k=1)[0]

            if tid == "teacher01" and p2 < 24 and rng.random() < 0.45:
                p2 += 8
            if tid == "park_edu" and p1 < 16 and rng.random() < 0.35:
                p1 = min(20, p1 + 4)

            total = p1 + p2 + p3 + p4
            if total >= 86:
                p2 = max(0, p2 - 16)
                total = p1 + p2 + p3 + p4

            nick = f"{rng.choice(first_chars)}수험{1000 + i}"
            ts = (base_dt + timedelta(minutes=i * 17)).strftime("%Y-%m-%d %H:%M:%S")
            rows.append(("sample_01", tid, nick, p1, p2, p3, p4, total, int(total >= PASS_THRESHOLD), "[]", ts))

        for exam_id, count in (("2026_01", 124), ("2026_02", 86)):
            for i in range(count):
                tid = rng.choices(teacher_names, weights=teacher_weights, k=1)[0]
                p1 = rng.choices(p1_choices, weights=p1_weights, k=1)[0]
                p2 = rng.choices(p2_choices, weights=p2_weights, k=1)[0]
                p3 = rng.choices(p3_choices, weights=p3_weights, k=1)[0]
                p4 = rng.choices(p4_choices, weights=p4_weights, k=1)[0]
                total = p1 + p2 + p3 + p4
                nick = f"{rng.choice(first_chars)}모의{200 + i}"
                ts = (base_dt + timedelta(minutes=i * 23)).strftime("%Y-%m-%d %H:%M:%S")
                rows.append((exam_id, tid, nick, p1, p2, p3, p4, total, int(total >= PASS_THRESHOLD), "[]", ts))

        return rows

    @staticmethod
    def _row_to_student(row: sqlite3.Row) -> StudentProfile:
        return StudentProfile(
            id=int(row["id"]),
            login_id=str(row["login_id"]),
            display_nickname=str(row["display_nickname"]),
            default_teacher_code=str(row["default_teacher_code"] or ""),
            status=str(row["status"] or "active"),
            created_at=str(row["created_at"]),
            last_login_at=str(row["last_login_at"]) if row["last_login_at"] else None,
        )

    # ---------- Student Auth & Sessions ----------

    def create_student(
        self,
        login_id: str,
        password_hash: str,
        display_nickname: str,
        default_teacher_code: str = "",
    ) -> StudentProfile:
        now_str = datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO students (
                        login_id, password_hash, display_nickname,
                        default_teacher_code, status, created_at
                    ) VALUES (?, ?, ?, ?, 'active', ?)
                    """,
                    (
                        login_id.strip(),
                        password_hash,
                        display_nickname.strip(),
                        default_teacher_code.strip(),
                        now_str,
                    ),
                )
                student_id = int(cursor.lastrowid or 0)
                row = conn.execute(
                    "SELECT * FROM students WHERE id = ?", (student_id,)
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise DuplicateLoginIdError("이미 사용 중인 아이디입니다.") from exc
        assert row is not None
        return self._row_to_student(row)

    def get_student_by_login_id(
        self, login_id: str
    ) -> tuple[StudentProfile, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM students WHERE login_id = ? LIMIT 1",
                (login_id.strip(),),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_student(row), str(row["password_hash"])

    def get_student_by_id(self, student_id: int) -> StudentProfile | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM students WHERE id = ? LIMIT 1", (student_id,)
            ).fetchone()
        return self._row_to_student(row) if row is not None else None

    def update_last_login(self, student_id: int) -> None:
        now_str = datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            conn.execute(
                "UPDATE students SET last_login_at = ? WHERE id = ?",
                (now_str, student_id),
            )

    def create_session(self, student_id: int, token_hash: str, expires_at: str) -> None:
        now_str = datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_sessions (student_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (student_id, token_hash, expires_at, now_str),
            )

    def get_student_by_session_token(
        self, token_hash: str, now_iso: str
    ) -> StudentProfile | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.*
                FROM user_sessions us
                JOIN students s ON s.id = us.student_id
                WHERE us.token_hash = ? AND us.expires_at > ? AND s.status = 'active'
                LIMIT 1
                """,
                (token_hash, now_iso),
            ).fetchone()
        return self._row_to_student(row) if row is not None else None

    def delete_session(self, token_hash: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM user_sessions WHERE token_hash = ?",
                (token_hash,),
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
        """Persist a graded submission and return (submission_id, created_at)."""
        ts = created_at or datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M:%S")
        nick = student_nickname.strip() or "익명"
        teacher = teacher_id.strip()
        safe_ext = file_ext if file_ext in (".xlsx", ".xlsm") else ""
        deductions_json = json.dumps([d.model_dump() for d in deductions], ensure_ascii=False)

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO submissions (
                    student_id, exam_id, teacher_id, student_nickname,
                    score_p1, score_p2, score_p3, score_p4,
                    total_score, passed, file_ext, deductions_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    student_id,
                    exam_id,
                    teacher,
                    nick,
                    scores.problem1,
                    scores.problem2,
                    scores.problem3,
                    scores.problem4,
                    scores.total,
                    int(passed),
                    safe_ext,
                    deductions_json,
                    ts,
                ),
            )
            submission_id = int(cursor.lastrowid or 0)
            if deductions:
                conn.executemany(
                    """
                    INSERT INTO submission_deductions (
                        submission_id, problem_no, task_name, deduction, detail
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (submission_id, d.problem_no, d.task_name, d.deduction, d.detail)
                        for d in deductions
                    ],
                )
        return submission_id, ts

    def get_summary(self, exam_id: str) -> SummaryStats:
        """Return participant count and average score for an exam."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt, COALESCE(AVG(total_score), 0.0) AS avg_score
                FROM submissions
                WHERE exam_id = ?
                """,
                (exam_id,),
            ).fetchone()

        count = int(row["cnt"]) if row else 0
        avg = round(float(row["avg_score"]), 2) if row else 0.0
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
        """Return masked top student and teacher rankings for an exam."""
        with self._connect() as conn:
            student_rows = conn.execute(
                """
                SELECT student_nickname, total_score, created_at
                FROM submissions
                WHERE exam_id = ?
                ORDER BY total_score DESC, id ASC
                LIMIT ?
                """,
                (exam_id, student_limit),
            ).fetchall()

            teacher_rows = conn.execute(
                """
                SELECT
                    teacher_id,
                    COUNT(*) AS student_count,
                    AVG(total_score) AS avg_score
                FROM submissions
                WHERE exam_id = ? AND TRIM(teacher_id) != ''
                GROUP BY teacher_id
                HAVING COUNT(*) >= 1
                ORDER BY avg_score DESC, student_count DESC
                LIMIT ?
                """,
                (exam_id, teacher_limit),
            ).fetchall()

        students = build_student_ranking_items([dict(r) for r in student_rows])
        teachers = [
            TeacherRankingItem(
                rank=idx + 1,
                teacher_id=mask_name(str(r["teacher_id"])),
                masked_teacher_id=mask_name(str(r["teacher_id"])),
                student_count=int(r["student_count"]),
                average_score=round(float(r["avg_score"]), 2),
            )
            for idx, r in enumerate(teacher_rows)
        ]
        return students, teachers

    def get_statistics(
        self,
        exam_id: str,
        my_scores: SectionScores | None = None,
    ) -> tuple[int, float, dict[str, ChartSeries]]:
        """Build histogram series for total score and each of the 4 sections."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT score_p1, score_p2, score_p3, score_p4, total_score
                FROM submissions
                WHERE exam_id = ?
                """,
                (exam_id,),
            ).fetchall()

        return build_statistics_charts([dict(r) for r in rows], my_scores=my_scores)

    def get_student_submissions(
        self,
        student_id: int,
        exam_id: str | None = None,
        limit: int = 50,
    ) -> list[StudentSubmissionItem]:
        query = """
            SELECT id, exam_id, teacher_id, student_nickname,
                   score_p1, score_p2, score_p3, score_p4,
                   total_score, passed, file_ext, deductions_json, created_at
            FROM submissions
            WHERE student_id = ?
        """
        params: list[object] = [student_id]
        if exam_id:
            query += " AND exam_id = ?"
            params.append(exam_id)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            StudentSubmissionItem(
                id=int(r["id"]),
                exam_id=str(r["exam_id"]),
                teacher_id=str(r["teacher_id"] or ""),
                student_nickname=str(r["student_nickname"] or "익명"),
                scores=SectionScores(
                    problem1=int(r["score_p1"]),
                    problem2=int(r["score_p2"]),
                    problem3=int(r["score_p3"]),
                    problem4=int(r["score_p4"]),
                    total=int(r["total_score"]),
                ),
                passed=bool(r["passed"]),
                file_ext=str(r["file_ext"] or ""),
                deductions=parse_deductions(r["deductions_json"]),
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]

    def get_student_latest_scores(
        self, student_id: int, exam_id: str
    ) -> SectionScores | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT score_p1, score_p2, score_p3, score_p4, total_score
                FROM submissions
                WHERE student_id = ? AND exam_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (student_id, exam_id),
            ).fetchone()
        if row is None:
            return None
        return SectionScores(
            problem1=int(row["score_p1"]),
            problem2=int(row["score_p2"]),
            problem3=int(row["score_p3"]),
            problem4=int(row["score_p4"]),
            total=int(row["total_score"]),
        )


_repository_instance: SubmissionRepository | SupabaseRepository | None = None
_repository_key: tuple[str, str] | None = None


def get_repository() -> SubmissionRepository | SupabaseRepository:
    """Return a singleton repository matching the configured backend (Supabase or SQLite)."""
    global _repository_instance, _repository_key
    backend = get_storage_backend()
    if backend == "supabase":
        url = get_supabase_url()
        key = get_supabase_service_role_key()
        current_key = ("supabase", f"{url}:{key[:8]}")
        if _repository_instance is None or _repository_key != current_key:
            _repository_instance = SupabaseRepository(url, key)
            _repository_key = current_key
        return _repository_instance

    current_path = get_db_path()
    current_key = ("sqlite", str(current_path))
    if _repository_instance is None or _repository_key != current_key:
        _repository_instance = SubmissionRepository(current_path)
        _repository_key = current_key
    return _repository_instance
