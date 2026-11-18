"""Shared repository helpers, domain exceptions, masking, and aggregation builders."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from comlicense_grader.config import SECTION_LABELS
from comlicense_grader.models.schemas import (
    ChartBucket,
    ChartSeries,
    DeductionItem,
    SectionScores,
    StudentHistorySummary,
    StudentRankingItem,
    StudentSubmissionItem,
    TeacherRankingItem,
)

KST = timezone(timedelta(hours=9))


class DuplicateLoginIdError(Exception):
    """Raised when attempting to register with an already-existing login_id."""


class RepositoryConnectionError(Exception):
    """Raised when the remote database backend cannot be reached or returns an unexpected error."""


def mask_name(name: str) -> str:
    """Mask a nickname or teacher code while preserving its leading character."""
    cleaned = name.strip()
    if not cleaned:
        return "********"
    if len(cleaned) == 1:
        return f"{cleaned}*******"
    star_count = max(len(cleaned) - 1, 7)
    return f"{cleaned[0]}{'*' * star_count}"


def format_kst_timestamp(raw_ts: str | None) -> str:
    """Format an ISO or SQLite timestamp string into KST 'YYYY-MM-DD HH:MM:SS'."""
    if not raw_ts:
        return ""
    cleaned = raw_ts.strip()
    # Already in 'YYYY-MM-DD HH:MM:SS' format without timezone offset
    if len(cleaned) == 19 and "T" not in cleaned and "+" not in cleaned and not cleaned.endswith("Z"):
        return cleaned
    try:
        normalized = cleaned.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return cleaned[:19].replace("T", " ")


def build_range_chart(
    title: str,
    values: list[int],
    ranges: list[tuple[int, int, str]],
    my_val: int | None,
) -> ChartSeries:
    """Bucket numeric scores into histogram slices and flag the user's slice."""
    total = len(values)
    buckets: list[ChartBucket] = []
    for low, high, label in ranges:
        cnt = sum(1 for v in values if low <= v <= high)
        pct = round((cnt / total) * 100, 1) if total > 0 else 0.0
        is_my = my_val is not None and low <= my_val <= high
        buckets.append(ChartBucket(label=label, count=cnt, percent=pct, is_my=is_my))
    return ChartSeries(title=title, buckets=buckets)


def build_statistics_charts(
    rows: list[dict[str, Any]],
    my_scores: SectionScores | None = None,
) -> tuple[int, float, dict[str, ChartSeries]]:
    """Build total and section histogram charts from submission score rows."""
    total_count = len(rows)
    total_vals = [int(r["total_score"]) for r in rows]
    p1_vals = [int(r["score_p1"]) for r in rows]
    p2_vals = [int(r["score_p2"]) for r in rows]
    p3_vals = [int(r["score_p3"]) for r in rows]
    p4_vals = [int(r["score_p4"]) for r in rows]

    avg_score = round(sum(total_vals) / total_count, 2) if total_count > 0 else 0.0

    charts: dict[str, ChartSeries] = {
        "total": build_range_chart(
            title=SECTION_LABELS["total"],
            values=total_vals,
            ranges=[
                (i * 10, i * 10 + 9 if i < 9 else 100, f"{i*10}~{i*10+9 if i < 9 else 100}")
                for i in range(10)
            ],
            my_val=my_scores.total if my_scores else None,
        ),
        "problem1": build_range_chart(
            title=SECTION_LABELS["problem1"],
            values=p1_vals,
            ranges=[(0, 4, "0~4"), (5, 9, "5~9"), (10, 14, "10~14"), (15, 19, "15~19"), (20, 20, "20")],
            my_val=my_scores.problem1 if my_scores else None,
        ),
        "problem2": build_range_chart(
            title=SECTION_LABELS["problem2"],
            values=p2_vals,
            ranges=[(0, 7, "0"), (8, 15, "8"), (16, 23, "16"), (24, 31, "24"), (32, 39, "32"), (40, 40, "40")],
            my_val=my_scores.problem2 if my_scores else None,
        ),
        "problem3": build_range_chart(
            title=SECTION_LABELS["problem3"],
            values=p3_vals,
            ranges=[(0, 9, "0"), (10, 19, "10"), (20, 20, "20")],
            my_val=my_scores.problem3 if my_scores else None,
        ),
        "problem4": build_range_chart(
            title=SECTION_LABELS["problem4"],
            values=p4_vals,
            ranges=[(0, 4, "0~4"), (5, 9, "5~9"), (10, 14, "10~14"), (15, 19, "15~19"), (20, 20, "20")],
            my_val=my_scores.problem4 if my_scores else None,
        ),
    }
    return total_count, avg_score, charts


def aggregate_teacher_rankings(
    rows: list[dict[str, Any]],
    teacher_limit: int = 5,
) -> list[TeacherRankingItem]:
    """Compute top teachers ranked by average score and submission count."""
    grouped: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        tid = str(row.get("teacher_id") or "").strip()
        if tid:
            grouped[tid].append(int(row["total_score"]))

    sorted_groups = sorted(
        grouped.items(),
        key=lambda item: (sum(item[1]) / len(item[1]), len(item[1])),
        reverse=True,
    )[:teacher_limit]

    return [
        TeacherRankingItem(
            rank=idx + 1,
            teacher_id=mask_name(tid),
            masked_teacher_id=mask_name(tid),
            student_count=len(scores),
            average_score=round(sum(scores) / len(scores), 2),
        )
        for idx, (tid, scores) in enumerate(sorted_groups)
    ]


def build_student_ranking_items(rows: list[dict[str, Any]]) -> list[StudentRankingItem]:
    """Convert raw student submission rows into masked ranking items."""
    return [
        StudentRankingItem(
            rank=idx + 1,
            nickname=mask_name(str(r["student_nickname"])),
            masked_nickname=mask_name(str(r["student_nickname"])),
            score=int(r["total_score"]),
            created_at=format_kst_timestamp(str(r["created_at"])),
        )
        for idx, r in enumerate(rows)
    ]


def build_student_history_summary(
    submissions: list[StudentSubmissionItem],
) -> StudentHistorySummary:
    """Compute overall attempt, pass rate, best, and average score for a student."""
    total_attempts = len(submissions)
    if total_attempts == 0:
        return StudentHistorySummary()

    pass_count = sum(1 for item in submissions if item.passed)
    scores = [item.scores.total for item in submissions]
    return StudentHistorySummary(
        total_attempts=total_attempts,
        pass_count=pass_count,
        pass_rate=round((pass_count / total_attempts) * 100, 1),
        best_score=max(scores),
        average_score=round(sum(scores) / total_attempts, 2),
    )


def parse_deductions(raw: Any) -> list[DeductionItem]:
    """Normalize JSONB list or JSON string into DeductionItem models."""
    if not raw:
        return []
    items = raw
    if isinstance(raw, str):
        import json

        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(items, list):
        return []
    result: list[DeductionItem] = []
    for item in items:
        if isinstance(item, dict):
            result.append(DeductionItem(**item))
    return result
