"""Integration and unit tests for the comlicense grading web application."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from comlicense_grader.config import DATA_DIR, EXAMS_DIR
from comlicense_grader.db import repository as repo_module
from comlicense_grader.grader.engine import get_engine
from comlicense_grader.main import app


@pytest.fixture()
def isolated_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a FastAPI TestClient backed by an isolated temporary SQLite database."""
    db_file = tmp_path / "test_comlicense.db"
    monkeypatch.setenv("COMLICENSE_DB_PATH", str(db_file))
    repo_module._repository_instance = None
    repo_module._repository_key = None
    with TestClient(app) as client:
        yield client
    repo_module._repository_instance = None
    repo_module._repository_key = None


def test_html_pages_and_static_assets(isolated_client: TestClient) -> None:
    for path in ("/", "/history", "/statistics", "/criteria", "/help", "/health"):
        resp = isolated_client.get(path)
        assert resp.status_code == 200, f"GET {path} failed with {resp.status_code}"

    home_html = isolated_client.get("/").text
    assert "/static/css/common.css" in home_html
    assert "/static/css/main-page.css" in home_html
    assert "/static/js/auth.js" in home_html
    assert "/static/js/main-page.js" in home_html

    history_html = isolated_client.get("/history").text
    assert "/static/css/history-page.css" in history_html
    assert "/static/js/history-page.js" in history_html

    stats_html = isolated_client.get("/statistics").text
    assert "/static/css/statistics-page.css" in stats_html
    assert "/static/js/statistics-page.js" in stats_html

    criteria_html = isolated_client.get("/criteria").text
    assert "/static/css/criteria-page.css" in criteria_html
    assert "/static/js/criteria-page.js" in criteria_html

    for asset in (
        "/static/css/common.css",
        "/static/css/main-page.css",
        "/static/css/history-page.css",
        "/static/css/statistics-page.css",
        "/static/css/criteria-page.css",
        "/static/js/nav.js",
        "/static/js/auth.js",
        "/static/js/main-page.js",
        "/static/js/history-page.js",
        "/static/js/statistics-page.js",
        "/static/js/criteria-page.js",
    ):
        asset_resp = isolated_client.get(asset)
        assert asset_resp.status_code == 200, f"Asset {asset} failed"


def test_exams_download_summary_rankings_statistics(isolated_client: TestClient) -> None:
    exams_resp = isolated_client.get("/api/exams")
    assert exams_resp.status_code == 200
    exams = exams_resp.json()["exams"]
    assert len(exams) >= 1
    assert exams[0]["exam_id"] == "sample_01"

    sheet_resp = isolated_client.get("/api/exams/sample_01/problem-sheet")
    assert sheet_resp.status_code == 200
    assert "대표기출따라하기 문제지" in sheet_resp.text

    dl_resp = isolated_client.get("/api/exams/sample_01/download")
    assert dl_resp.status_code == 200
    assert len(dl_resp.content) > 1000
    with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as dl_zf:
        names = dl_zf.namelist()
        assert any(n.endswith(".xlsm") for n in names)
        assert any(n.endswith(".html") for n in names)

    raw_resp = isolated_client.get("/api/exams/sample_01/download?raw=true")
    assert raw_resp.status_code == 200
    assert len(raw_resp.content) > 1000

    zip_resp = isolated_client.get("/api/exams/download-all")
    assert zip_resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        assert len(zf.namelist()) >= 1

    summary_resp = isolated_client.get("/api/summary?exam_id=sample_01")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["participant_count"] == 2103
    assert summary["average_score"] > 0

    rankings_resp = isolated_client.get("/api/rankings?exam_id=sample_01")
    assert rankings_resp.status_code == 200
    rankings = rankings_resp.json()
    assert len(rankings["students"]) == 10
    assert len(rankings["teachers"]) == 5
    assert "*" in rankings["students"][0]["masked_nickname"]

    stats_resp = isolated_client.get(
        "/api/statistics?exam_id=sample_01&my=72&jum0=16&jum1=32&jum2=10&jum3=14"
    )
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert set(stats["charts"].keys()) == {"total", "problem1", "problem2", "problem3", "problem4"}
    assert any(b["is_my"] for b in stats["charts"]["total"]["buckets"])
    assert any(b["is_my"] for b in stats["charts"]["problem2"]["buckets"])


def test_grade_endpoint_with_sample_workbook_and_invalid_extension(
    isolated_client: TestClient,
) -> None:
    sample_xlsm = EXAMS_DIR / "sample_01" / "question.xlsm"
    assert sample_xlsm.exists()

    with sample_xlsm.open("rb") as f:
        resp = isolated_client.post(
            "/api/grade",
            data={
                "exam_id": "sample_01",
                "teacher_id": "teacher01",
                "student_nickname": "홍길동",
            },
            files={"file": ("문제샘플.xlsm", f, "application/vnd.ms-excel.sheet.macroEnabled.12")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["exam_id"] == "sample_01"
    assert body["scores"]["total"] == 0
    assert body["passed"] is False
    assert len(body["deductions"]) > 0
    assert body["summary"]["participant_count"] == 2104

    bad_resp = isolated_client.post(
        "/api/grade",
        data={"exam_id": "sample_01", "teacher_id": "t1", "student_nickname": "학생"},
        files={"file": ("bad.txt", b"not excel", "text/plain")},
    )
    assert bad_resp.status_code == 400


def test_partial_credit_and_all_or_nothing_rules(tmp_path: Path) -> None:
    """Verify 기본작업-1 (5pt all-or-nothing), 기본작업-2 (2pt*5 partial), 계산작업 (8pt*5 all-or-nothing)."""
    sample_xlsm = EXAMS_DIR / "sample_01" / "question.xlsm"
    work_xlsm = tmp_path / "partial_solve.xlsm"
    shutil.copy2(sample_xlsm, work_xlsm)

    spec_path = EXAMS_DIR / "sample_01" / "answer_spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    basic1_expected = spec["sections"]["basic"]["tasks"][0]["expected_cells"]

    wb = openpyxl.load_workbook(work_xlsm, keep_vba=True)

    # 1) Solve 기본작업-1 EXCEPT one wrong cell -> must be 0 points (all-or-nothing)
    ws_b1 = wb["기본작업-1"]
    for coord, val in basic1_expected.items():
        ws_b1[coord].value = val
    ws_b1["F8"].value = "오답값"

    # 2) Solve only item ① of 기본작업-2 (merge A1:F1 + bold + size>=14 + center) -> partial 2 pts
    ws_b2 = wb["기본작업-2"]
    ws_b2.merge_cells("A1:F1")
    ws_b2["A1"].font = openpyxl.styles.Font(size=16, bold=True)
    ws_b2["A1"].alignment = openpyxl.styles.Alignment(horizontal="center")

    # 3) Solve 계산작업 3번 (D24 average of 드라마 예매수량) using formula -> 8 pts
    ws_calc = wb["계산작업"]
    ws_calc["D24"].value = "=AVERAGE(D14,D16,D17,D18)"

    wb.save(work_xlsm)
    wb.close()

    scores, deductions, _, _ = get_engine().grade_file("sample_01", work_xlsm)
    assert scores.problem1 == 2, f"Expected 2 partial pts on problem1, got {scores.problem1}"
    assert scores.problem2 == 8, f"Expected 8 pts on problem2, got {scores.problem2}"
    assert scores.total == 10

    # Now fix F8 in 기본작업-1 -> problem1 should jump by +5 to 7 pts!
    wb2 = openpyxl.load_workbook(work_xlsm, keep_vba=True)
    wb2["기본작업-1"]["F8"].value = basic1_expected["F8"]
    wb2.save(work_xlsm)
    wb2.close()

    scores2, _, _, _ = get_engine().grade_file("sample_01", work_xlsm)
    assert scores2.problem1 == 7
    assert scores2.total == 15


def test_student_auth_pii_guards_and_my_submission_history(
    isolated_client: TestClient,
) -> None:
    # Unauthenticated check
    me_guest = isolated_client.get("/api/auth/me")
    assert me_guest.status_code == 200
    assert me_guest.json()["authenticated"] is False

    assert isolated_client.get("/api/my/submissions").status_code == 401

    # Reject email / phone PII in login_id and display_nickname
    bad_email = isolated_client.post(
        "/api/auth/register",
        json={
            "login_id": "student@example.com",
            "password": "password123!",
            "display_nickname": "코딩거북이",
        },
    )
    assert bad_email.status_code == 422

    bad_phone = isolated_client.post(
        "/api/auth/register",
        json={
            "login_id": "01012345678",
            "password": "password123!",
            "display_nickname": "코딩거북이",
        },
    )
    assert bad_phone.status_code == 422

    bad_nick_phone = isolated_client.post(
        "/api/auth/register",
        json={
            "login_id": "turtle_01",
            "password": "password123!",
            "display_nickname": "010-1234-5678",
        },
    )
    assert bad_nick_phone.status_code == 422

    # Valid registration sets session cookie
    reg_resp = isolated_client.post(
        "/api/auth/register",
        json={
            "login_id": "turtle_01",
            "password": "password123!",
            "display_nickname": "코딩거북이",
            "default_teacher_code": "teacher01",
        },
    )
    assert reg_resp.status_code == 201
    reg_body = reg_resp.json()
    assert reg_body["authenticated"] is True
    assert reg_body["student"]["login_id"] == "turtle_01"
    assert reg_body["student"]["display_nickname"] == "코딩거북이"

    # Duplicate login_id -> 409
    dup_resp = isolated_client.post(
        "/api/auth/register",
        json={
            "login_id": "turtle_01",
            "password": "password123!",
            "display_nickname": "다른별명",
        },
    )
    assert dup_resp.status_code == 409

    # Logout and verify /api/auth/me is false
    assert isolated_client.post("/api/auth/logout").status_code == 200
    assert isolated_client.get("/api/auth/me").json()["authenticated"] is False

    # Wrong password -> 401
    bad_login = isolated_client.post(
        "/api/auth/login",
        json={"login_id": "turtle_01", "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401

    # Valid login -> 200
    good_login = isolated_client.post(
        "/api/auth/login",
        json={"login_id": "turtle_01", "password": "password123!"},
    )
    assert good_login.status_code == 200
    assert good_login.json()["authenticated"] is True

    # Submit an exam while logged in (omit nickname/teacher to test defaults)
    sample_xlsm = EXAMS_DIR / "sample_01" / "question.xlsm"
    with sample_xlsm.open("rb") as f:
        grade_resp = isolated_client.post(
            "/api/grade",
            data={"exam_id": "sample_01"},
            files={"file": ("실명포함파일_홍길동.xlsm", f, "application/vnd.ms-excel.sheet.macroEnabled.12")},
        )
    assert grade_resp.status_code == 200
    grade_data = grade_resp.json()
    assert grade_data["student_id"] == reg_body["student"]["id"]
    assert grade_data["student_nickname"] == "코딩거북이"
    assert grade_data["teacher_id"] == "teacher01"

    # Verify /api/my/submissions records it without storing original filename
    hist_resp = isolated_client.get("/api/my/submissions")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["summary"]["total_attempts"] == 1
    assert len(hist_data["submissions"]) == 1
    assert hist_data["submissions"][0]["file_ext"] == ".xlsm"
    assert len(hist_data["submissions"][0]["deductions"]) > 0

    # Verify /api/statistics automatically highlights logged-in student's latest score
    stats_resp = isolated_client.get("/api/statistics?exam_id=sample_01")
    assert stats_resp.status_code == 200
    stats_data = stats_resp.json()
    assert stats_data["my_scores"] is not None
    assert stats_data["my_scores"]["total"] == grade_data["scores"]["total"]
    assert any(b["is_my"] for b in stats_data["charts"]["total"]["buckets"])


def test_supabase_repository_rest_integration_with_mock_transport() -> None:
    import httpx

    from comlicense_grader.db.supabase_repository import SupabaseRepository
    from comlicense_grader.models.schemas import DeductionItem, SectionScores

    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        assert request.headers["apikey"] == "test-service-key"
        assert request.headers["authorization"] == "Bearer test-service-key"

        if request.method == "POST" and request.url.path.endswith("/students"):
            return httpx.Response(
                201,
                json=[
                    {
                        "id": 7,
                        "login_id": "supa_student",
                        "display_nickname": "수파학습자",
                        "default_teacher_code": "teacher01",
                        "status": "active",
                        "created_at": "2026-11-18T12:00:00Z",
                        "last_login_at": None,
                    }
                ],
            )
        if request.method == "POST" and request.url.path.endswith("/submissions"):
            body = json.loads(request.content.decode("utf-8"))
            assert body["student_id"] == 7
            assert body["file_ext"] == ".xlsm"
            return httpx.Response(
                201,
                json=[
                    {
                        "id": 99,
                        "created_at": "2026-11-18T12:05:00Z",
                    }
                ],
            )
        if request.method == "POST" and request.url.path.endswith("/submission_deductions"):
            return httpx.Response(201, json=[])
        if request.method == "GET" and request.url.path.endswith("/submissions"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 99,
                        "exam_id": "sample_01",
                        "teacher_id": "teacher01",
                        "student_nickname": "수파학습자",
                        "score_p1": 20,
                        "score_p2": 32,
                        "score_p3": 20,
                        "score_p4": 18,
                        "total_score": 90,
                        "passed": True,
                        "file_ext": ".xlsm",
                        "deductions_json": [
                            {
                                "problem_no": 2,
                                "task_name": "계산작업-1",
                                "deduction": 8,
                                "detail": "수식 오류",
                            }
                        ],
                        "created_at": "2026-11-18T12:05:00Z",
                    }
                ],
            )
        return httpx.Response(200, json=[])

    repo = SupabaseRepository("https://example.supabase.co", "test-service-key")
    repo._client = httpx.Client(
        base_url=repo.rest_url,
        headers=repo.headers,
        transport=httpx.MockTransport(handler),
    )

    student = repo.create_student("supa_student", "scrypt$16384$8$1$aa$bb", "수파학습자", "teacher01")
    assert student.id == 7

    sub_id, graded_at = repo.save_submission(
        exam_id="sample_01",
        teacher_id="teacher01",
        student_nickname="수파학습자",
        scores=SectionScores(problem1=20, problem2=32, problem3=20, problem4=18, total=90),
        passed=True,
        deductions=[DeductionItem(problem_no=2, task_name="계산작업-1", deduction=8, detail="수식 오류")],
        student_id=7,
        file_ext=".xlsm",
    )
    assert sub_id == 99
    assert graded_at == "2026-11-18 21:05:00"

    history = repo.get_student_submissions(student_id=7)
    assert len(history) == 1
    assert history[0].scores.total == 90
    assert history[0].deductions[0].task_name == "계산작업-1"
    assert ("POST", "/rest/v1/submission_deductions") in calls
