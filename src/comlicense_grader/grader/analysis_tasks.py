"""Grader for Problem 3: 분석작업 (Goal Seek, Consolidate, PivotTable; 2 × 10 pts = 20 pts)."""

from __future__ import annotations

from typing import Any

from comlicense_grader.grader.base import (
    SectionResult,
    WorkbookContext,
    values_match,
)
from comlicense_grader.grader.calc_tasks import evaluate_excel_formula
from comlicense_grader.models.schemas import DeductionItem


def grade_analysis_tasks(ctx: WorkbookContext, section_spec: dict[str, Any]) -> SectionResult:
    """Grade both analysis tasks (each 10 pts, no partial credit)."""
    problem_no = int(section_spec.get("problem_no", 3))
    max_score = int(section_spec.get("max_score", 20))
    tasks = section_spec.get("tasks", [])

    earned = 0
    deductions: list[DeductionItem] = []

    for task in tasks:
        check_type = task.get("check_type", "")
        if check_type == "goal_seek":
            pts, item_deduction = _grade_goal_seek(ctx, problem_no, task)
        elif check_type == "consolidate":
            pts, item_deduction = _grade_consolidate(ctx, problem_no, task)
        elif check_type == "pivot_table":
            pts, item_deduction = _grade_pivot_table(ctx, problem_no, task)
        else:
            pts = 0
            item_deduction = DeductionItem(
                problem_no=problem_no,
                task_name=task.get("task_name", "분석작업"),
                deduction=int(task.get("max_score", 10)),
                detail="지원되지 않는 분석작업 채점 규칙입니다.",
            )
        earned += pts
        if item_deduction is not None:
            deductions.append(item_deduction)

    return SectionResult(
        problem_no=problem_no,
        score=min(earned, max_score),
        max_score=max_score,
        deductions=deductions,
    )


def _grade_goal_seek(
    ctx: WorkbookContext, problem_no: int, task: dict[str, Any]
) -> tuple[int, DeductionItem | None]:
    sheet_name = task.get("sheet", "분석작업-1")
    task_name = task.get("task_name", "분석작업-1 (목표값 찾기)")
    max_pts = int(task.get("max_score", 10))

    ws_f = ctx.get_sheet(sheet_name, values=False)
    ws_v = ctx.get_sheet(sheet_name, values=True)
    if ws_f is None:
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail=f"'{sheet_name}' 시트를 찾을 수 없습니다.",
        )

    target_cell = task.get("target_cell", "E6")
    variable_cell = task.get("variable_cell", "B4")
    target_value = float(task.get("target_value", 20000000))
    tolerance = float(task.get("tolerance", 1000))
    initial_var = task.get("initial_variable_value")
    require_formula = bool(task.get("require_formula_on_target", True))

    raw_target = ws_f[target_cell].value
    if require_formula and not (isinstance(raw_target, str) and raw_target.strip().startswith("=")):
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail=f"목표 셀({target_cell})의 수식이 유지되지 않았습니다.",
        )

    var_val = ws_v[variable_cell].value if ws_v is not None else ws_f[variable_cell].value
    if var_val is None:
        var_val = ws_f[variable_cell].value

    # Check if target cell cached/evaluated value matches target_value
    cached_target = ws_v[target_cell].value if ws_v is not None else None
    if cached_target is None and isinstance(raw_target, str) and raw_target.strip().startswith("="):
        cached_target = evaluate_excel_formula(ws_f, raw_target.strip())

    if cached_target is None:
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail=f"목표값 찾기 결과({target_cell})를 확인할 수 없습니다.",
        )

    if initial_var is not None and values_match(var_val, initial_var, tolerance=1e-4):
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail=f"목표값 찾기 미수행 (변수 셀 {variable_cell}이 초기값 그대로입니다).",
        )

    if not values_match(cached_target, target_value, tolerance=tolerance):
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail=f"목표 셀({target_cell})의 결과값이 목표값과 일치하지 않습니다.",
        )

    return max_pts, None


def _grade_consolidate(
    ctx: WorkbookContext, problem_no: int, task: dict[str, Any]
) -> tuple[int, DeductionItem | None]:
    sheet_name = task.get("sheet", "분석작업-2")
    task_name = task.get("task_name", "분석작업-2 (데이터 통합)")
    max_pts = int(task.get("max_score", 10))
    tolerance = float(task.get("tolerance", 0.01))

    ws_f = ctx.get_sheet(sheet_name, values=False)
    ws_v = ctx.get_sheet(sheet_name, values=True)
    if ws_f is None:
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail=f"'{sheet_name}' 시트를 찾을 수 없습니다.",
        )

    expected_cells: dict[str, Any] = task.get("expected_cells", {})
    mismatches: list[str] = []
    for coord, expected in expected_cells.items():
        val = ws_v[coord].value if ws_v is not None else None
        if val is None:
            raw = ws_f[coord].value
            if isinstance(raw, str) and raw.strip().startswith("="):
                val = evaluate_excel_formula(ws_f, raw.strip())
            else:
                val = raw
        if not values_match(val, expected, tolerance=tolerance):
            mismatches.append(coord)

    if mismatches:
        sample = ", ".join(mismatches[:3])
        extra = f" 외 {len(mismatches) - 3}개" if len(mismatches) > 3 else ""
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail=f"통합 결과 누락 또는 값 불일치 ({sample}{extra})",
        )
    return max_pts, None


def _grade_pivot_table(
    ctx: WorkbookContext, problem_no: int, task: dict[str, Any]
) -> tuple[int, DeductionItem | None]:
    task_name = task.get("task_name", "분석작업 (피벗 테이블)")
    max_pts = int(task.get("max_score", 10))

    pivot_paths = ctx.list_zip("xl/pivotTables/pivotTable", ".xml")
    if not pivot_paths:
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail="피벗 테이블이 생성되지 않았습니다.",
        )

    pivot_xml = ctx.read_xml(pivot_paths[0])
    if pivot_xml is None:
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail="피벗 테이블 XML 구조를 읽을 수 없습니다.",
        )

    expected_location = task.get("expected_location")
    if expected_location:
        loc_el = pivot_xml.find(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}location")
        ref = loc_el.attrib.get("ref", "") if loc_el is not None else ""
        if expected_location not in ref:
            return 0, DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=max_pts,
                detail=f"피벗 테이블 위치가 올바르지 않습니다 (기대: {expected_location}).",
            )

    return max_pts, None
