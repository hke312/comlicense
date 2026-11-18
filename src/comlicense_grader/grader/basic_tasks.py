"""Grader for Problem 1: 기본작업 (기본작업-1, 기본작업-2, 기본작업-3, max 20 pts)."""

from __future__ import annotations

from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from comlicense_grader.grader.base import (
    SectionResult,
    WorkbookContext,
    iter_range_coords,
    values_match,
)
from comlicense_grader.models.schemas import DeductionItem


def grade_basic_tasks(ctx: WorkbookContext, section_spec: dict[str, Any]) -> SectionResult:
    """Grade all basic tasks (기본작업-1, 기본작업-2, 기본작업-3)."""
    problem_no = int(section_spec.get("problem_no", 1))
    max_score = int(section_spec.get("max_score", 20))
    tasks = section_spec.get("tasks", [])

    earned = 0
    deductions: list[DeductionItem] = []

    for task in tasks:
        check_type = task.get("check_type", "")
        if check_type == "cell_values":
            pts, item_deductions = _grade_cell_values(ctx, problem_no, task)
        elif check_type == "formatting_items":
            pts, item_deductions = _grade_formatting_items(ctx, problem_no, task)
        elif check_type == "filter_or_cf":
            pts, item_deductions = _grade_filter_or_cf(ctx, problem_no, task)
        else:
            pts, item_deductions = 0, [
                DeductionItem(
                    problem_no=problem_no,
                    task_name=task.get("task_name", "기본작업"),
                    deduction=int(task.get("max_score", 0)),
                    detail="지원되지 않는 채점 규칙입니다.",
                )
            ]
        earned += pts
        deductions.extend(item_deductions)

    return SectionResult(
        problem_no=problem_no,
        score=min(earned, max_score),
        max_score=max_score,
        deductions=deductions,
    )


def _grade_cell_values(
    ctx: WorkbookContext, problem_no: int, task: dict[str, Any]
) -> tuple[int, list[DeductionItem]]:
    sheet_name = task.get("sheet", "기본작업-1")
    task_name = task.get("task_name", "기본작업-1 (데이터 입력)")
    max_pts = int(task.get("max_score", 5))
    ws = ctx.get_sheet(sheet_name, values=True) or ctx.get_sheet(sheet_name, values=False)

    if ws is None:
        return 0, [
            DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=max_pts,
                detail=f"'{sheet_name}' 시트를 찾을 수 없습니다.",
            )
        ]

    expected_cells: dict[str, Any] = task.get("expected_cells", {})
    mismatches: list[str] = []
    for coord, expected in expected_cells.items():
        actual = ws[coord].value
        if not values_match(actual, expected):
            mismatches.append(coord)

    if mismatches:
        sample = ", ".join(mismatches[:3])
        extra = f" 외 {len(mismatches) - 3}건" if len(mismatches) > 3 else ""
        return 0, [
            DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=max_pts,
                detail=f"데이터 입력 누락 또는 불일치 ({sample}{extra})",
            )
        ]
    return max_pts, []


def _grade_formatting_items(
    ctx: WorkbookContext, problem_no: int, task: dict[str, Any]
) -> tuple[int, list[DeductionItem]]:
    sheet_name = task.get("sheet", "기본작업-2")
    ws = ctx.get_sheet(sheet_name, values=False)
    items = task.get("items", [])

    if ws is None:
        total_pts = int(task.get("max_score", 10))
        return 0, [
            DeductionItem(
                problem_no=problem_no,
                task_name=task.get("task_name", "기본작업-2"),
                deduction=total_pts,
                detail=f"'{sheet_name}' 시트를 찾을 수 없습니다.",
            )
        ]

    earned = 0
    deductions: list[DeductionItem] = []

    for item in items:
        pts = int(item.get("points", 2))
        name = item.get("name", "기본작업-2 서식")
        rule = item.get("rule", "")

        ok, detail = _check_format_rule(ctx, ws, rule, item)
        if ok:
            earned += pts
        else:
            deductions.append(
                DeductionItem(
                    problem_no=problem_no,
                    task_name=name,
                    deduction=pts,
                    detail=detail,
                )
            )
    return earned, deductions


def _check_format_rule(
    ctx: WorkbookContext, ws: Worksheet, rule: str, item: dict[str, Any]
) -> tuple[bool, str]:
    merged_strs = {str(rng) for rng in ws.merged_cells.ranges}

    if rule == "title_format":
        merge_range = item.get("merge_range", "A1:F1")
        cell_coord = item.get("cell", "A1")
        min_size = float(item.get("min_font_size", 14))
        require_bold = bool(item.get("require_bold", True))
        expected_align = item.get("horizontal", "center")

        if merge_range not in merged_strs:
            return False, f"{merge_range} 셀 병합이 적용되지 않았습니다."
        cell = ws[cell_coord]
        if require_bold and not (cell.font and cell.font.bold):
            return False, f"{cell_coord} 제목 굵게 서식이 적용되지 않았습니다."
        if cell.font and cell.font.size and float(cell.font.size) < min_size:
            return False, f"{cell_coord} 글꼴 크기가 {int(min_size)}pt 미만입니다."
        if expected_align and (not cell.alignment or cell.alignment.horizontal != expected_align):
            return False, f"{cell_coord} 가로 가운데 맞춤이 적용되지 않았습니다."
        return True, ""

    if rule == "table_style":
        header_range = item.get("header_range", "A3:F3")
        border_range = item.get("border_range", "A3:F15")

        header_coords = iter_range_coords(header_range)
        filled_headers = sum(
            1
            for c in header_coords
            if ws[c].fill and ws[c].fill.fill_type not in (None, "none")
        )
        if filled_headers < len(header_coords):
            return False, f"{header_range} 머리글 영역 채우기(음영)가 누락되었습니다."

        border_coords = iter_range_coords(border_range)
        bordered = sum(1 for c in border_coords if _has_any_border(ws[c]))
        if bordered < len(border_coords):
            return False, f"{border_range} 표 테두리가 모두 적용되지 않았습니다."
        return True, ""

    if rule == "merge_groups":
        ranges = item.get("ranges", [])
        missing = [rng for rng in ranges if rng not in merged_strs]
        if missing:
            return False, f"셀 병합 누락 ({', '.join(missing[:2])})"
        return True, ""

    if rule == "number_format":
        checks = item.get("checks", [])
        for chk in checks:
            rng = chk.get("range", "")
            tokens = [t.lower() for t in chk.get("contains_any", [])]
            for coord in iter_range_coords(rng):
                fmt = (ws[coord].number_format or "").lower()
                if not any(tok in fmt for tok in tokens):
                    return False, f"{rng} 셀 표시 형식({coord})이 올바르지 않습니다."
        return True, ""

    if rule == "defined_name_or_cf":
        defined_name = item.get("defined_name", "")
        has_name = bool(defined_name and defined_name in ctx.wb_formulas.defined_names)
        has_cf = len(ws.conditional_formatting) > 0
        has_comment = any(
            cell.comment is not None
            for row in ws.iter_rows()
            for cell in row
        )
        if has_name or has_cf or has_comment:
            return True, ""
        return False, f"이름 정의('{defined_name}') 또는 메모/조건부 서식이 적용되지 않았습니다."

    return False, "서식 확인 규칙을 통과하지 못했습니다."


def _has_any_border(cell: Any) -> bool:
    if not cell.border:
        return False
    return any(
        side and side.style is not None
        for side in (cell.border.top, cell.border.bottom, cell.border.left, cell.border.right)
    )


def _grade_filter_or_cf(
    ctx: WorkbookContext, problem_no: int, task: dict[str, Any]
) -> tuple[int, list[DeductionItem]]:
    sheet_name = task.get("sheet", "기본작업-3")
    task_name = task.get("task_name", "기본작업-3 (고급필터/조건부서식)")
    max_pts = int(task.get("max_score", 5))
    ws = ctx.get_sheet(sheet_name, values=False)

    if ws is None:
        return 0, [
            DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=max_pts,
                detail=f"'{sheet_name}' 시트를 찾을 수 없습니다.",
            )
        ]

    mode = task.get("mode", "either")
    has_cf = len(ws.conditional_formatting) > 0

    dest_cell = task.get("filter_dest_cell", "A22")
    min_rows = int(task.get("min_filter_rows", 2))
    dest_row = ws[dest_cell].row
    dest_col = ws[dest_cell].column
    extracted_rows = 0
    for r in range(dest_row, ws.max_row + 1):
        if ws.cell(r, dest_col).value is not None:
            extracted_rows += 1
    has_filter_output = extracted_rows >= min_rows

    if mode == "conditional_formatting":
        passed = has_cf
        reason = "조건부 서식 규칙이 설정되지 않았습니다."
    elif mode == "advanced_filter":
        passed = has_filter_output
        reason = f"고급 필터 결과({dest_cell} 이하)가 추출되지 않았습니다."
    else:
        passed = has_cf or has_filter_output
        reason = "고급 필터 추출 결과 또는 조건부 서식이 적용되지 않았습니다."

    if passed:
        return max_pts, []
    return 0, [
        DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail=reason,
        )
    ]
