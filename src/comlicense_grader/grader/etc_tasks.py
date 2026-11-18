"""Grader for Problem 4: 기타작업 (매크로작업 10 pts + 차트작업 10 pts = 20 pts, partial credit)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from comlicense_grader.grader.base import (
    NS,
    SectionResult,
    WorkbookContext,
    iter_range_coords,
    values_match,
)
from comlicense_grader.grader.calc_tasks import evaluate_excel_formula
from comlicense_grader.models.schemas import DeductionItem

VML_MACRO_RE = re.compile(r"<x:FmlaMacro>([^<]+)</x:FmlaMacro>", re.IGNORECASE)


def grade_etc_tasks(ctx: WorkbookContext, section_spec: dict[str, Any]) -> SectionResult:
    """Grade macro and chart tasks (partial credit enabled per sub-item)."""
    problem_no = int(section_spec.get("problem_no", 4))
    max_score = int(section_spec.get("max_score", 20))
    tasks = section_spec.get("tasks", [])

    earned = 0
    deductions: list[DeductionItem] = []

    for task in tasks:
        check_type = task.get("check_type", "")
        if check_type == "macro_item":
            pts, item_deductions = _grade_macro_item(ctx, problem_no, task)
        elif check_type == "chart_item":
            pts, item_deductions = _grade_chart_item(ctx, problem_no, task)
        else:
            pts = 0
            item_deductions = [
                DeductionItem(
                    problem_no=problem_no,
                    task_name=task.get("task_name", "기타작업"),
                    deduction=int(task.get("max_score", 0)),
                    detail="지원되지 않는 기타작업 채점 규칙입니다.",
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


def _count_macro_linked_controls(ctx: WorkbookContext, sheet_name: str) -> int:
    """Count shapes/buttons linked to a VBA macro via DrawingML or VML."""
    count = 0

    drawing_paths = ctx.get_sheet_drawing_paths(sheet_name)
    if not drawing_paths:
        drawing_paths = ctx.list_zip("xl/drawings/drawing", ".xml")

    for dpath in drawing_paths:
        root = ctx.read_xml(dpath)
        if root is None:
            continue
        for elem in root.iter():
            macro_attr = elem.attrib.get("macro", "").strip()
            if macro_attr:
                count += 1

    # Also check VML form-control buttons (xl/drawings/vmlDrawing*.vml)
    for vml_path in ctx.list_zip("xl/drawings/vmlDrawing", ".vml"):
        raw = ctx.zip_entries.get(vml_path, b"").decode("utf-8", errors="ignore")
        matches = [m.strip() for m in VML_MACRO_RE.findall(raw) if m.strip()]
        count += len(matches)

    return count


def _grade_macro_item(
    ctx: WorkbookContext, problem_no: int, task: dict[str, Any]
) -> tuple[int, list[DeductionItem]]:
    sheet_name = task.get("sheet", "매크로작업")
    task_name = task.get("task_name", "매크로작업")
    macro_idx = int(task.get("macro_index", 1))
    vba_pts = int(task.get("vba_points", 3))
    btn_pts = int(task.get("button_points", 2))
    total_pts = vba_pts + btn_pts

    ws_f = ctx.get_sheet(sheet_name, values=False)
    ws_v = ctx.get_sheet(sheet_name, values=True)
    if ws_f is None:
        return 0, [
            DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=total_pts,
                detail=f"'{sheet_name}' 시트를 찾을 수 없습니다.",
            )
        ]

    has_vba = "xl/vbaProject.bin" in ctx.zip_entries
    linked_count = _count_macro_linked_controls(ctx, sheet_name)

    # Check worksheet result/effect for this macro item
    effect_ok = False
    if "expected_cells" in task:
        expected_cells: dict[str, Any] = task["expected_cells"]
        matches = 0
        for coord, exp in expected_cells.items():
            val = ws_v[coord].value if ws_v is not None else None
            if val is None:
                raw = ws_f[coord].value
                if isinstance(raw, str) and raw.strip().startswith("="):
                    val = evaluate_excel_formula(ws_f, raw.strip())
                else:
                    val = raw
            if values_match(val, exp, tolerance=0.01):
                matches += 1
        effect_ok = matches == len(expected_cells)
    elif "format_range" in task:
        coords = iter_range_coords(task["format_range"])
        styled = sum(
            1
            for c in coords
            if (ws_f[c].fill and ws_f[c].fill.fill_type not in (None, "none"))
            or (ws_f[c].font and ws_f[c].font.bold)
        )
        effect_ok = styled == len(coords)

    earned = 0
    deductions: list[DeductionItem] = []

    if has_vba and effect_ok:
        earned += vba_pts
    else:
        reason = (
            "VBA 매크로(vbaProject.bin)가 없습니다."
            if not has_vba
            else f"매크로 {macro_idx} 실행 결과(셀 값 또는 서식)가 반영되지 않았습니다."
        )
        deductions.append(
            DeductionItem(
                problem_no=problem_no,
                task_name=f"{task_name} - 매크로 기록",
                deduction=vba_pts,
                detail=reason,
            )
        )

    if has_vba and linked_count >= macro_idx:
        earned += btn_pts
    else:
        deductions.append(
            DeductionItem(
                problem_no=problem_no,
                task_name=f"{task_name} - 단추/도형 연결",
                deduction=btn_pts,
                detail=f"매크로 {macro_idx} 실행 도형/단추 연결이 확인되지 않았습니다.",
            )
        )

    return earned, deductions


def _grade_chart_item(
    ctx: WorkbookContext, problem_no: int, task: dict[str, Any]
) -> tuple[int, list[DeductionItem]]:
    sheet_name = task.get("sheet", "차트작업")
    task_name = task.get("task_name", "차트작업")
    pts = int(task.get("max_score", 2))
    rule = task.get("rule", "")

    chart_paths = ctx.get_sheet_chart_paths(sheet_name)
    if not chart_paths:
        chart_paths = ctx.list_zip("xl/charts/chart", ".xml")

    if not chart_paths:
        return 0, [
            DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=pts,
                detail=f"'{sheet_name}' 시트에 차트가 존재하지 않습니다.",
            )
        ]

    chart_xml = ctx.read_xml(chart_paths[0])
    if chart_xml is None:
        return 0, [
            DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=pts,
                detail="차트 XML을 파싱할 수 없습니다.",
            )
        ]

    ok, detail = _check_chart_rule(chart_xml, rule, task)
    if ok:
        return pts, []
    return 0, [
        DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=pts,
            detail=detail,
        )
    ]


def _check_chart_rule(
    chart_xml: ET.Element, rule: str, task: dict[str, Any]
) -> tuple[bool, str]:
    chart_el = chart_xml.find("c:chart", NS)
    if chart_el is None:
        return False, "차트 요소를 찾을 수 없습니다."

    if rule == "chart_title":
        auto_del = chart_el.find("c:autoTitleDeleted", NS)
        title_el = chart_el.find("c:title", NS)
        if title_el is not None and (auto_del is None or auto_del.attrib.get("val") != "1"):
            return True, ""
        return False, "차트 제목이 추가되지 않았습니다."

    if rule == "chart_type":
        expected_types = set(task.get("expected_types", ["barChart"]))
        plot_area = chart_el.find("c:plotArea", NS)
        if plot_area is None:
            return False, "차트 그림 영역(plotArea)을 찾을 수 없습니다."
        found_types = {
            child.tag.split("}", 1)[-1]
            for child in plot_area
            if child.tag.endswith("Chart")
        }
        if found_types & expected_types:
            return True, ""
        return False, f"차트 종류가 요구사항({', '.join(expected_types)})으로 변경되지 않았습니다."

    if rule == "legend_pos":
        allowed = set(task.get("allowed_positions", ["t", "b"]))
        legend_pos = chart_el.find("c:legend/c:legendPos", NS)
        pos_val = legend_pos.attrib.get("val") if legend_pos is not None else None
        if pos_val in allowed:
            return True, ""
        return False, f"범례 위치가 지정된 위치({', '.join(sorted(allowed))})로 변경되지 않았습니다."

    if rule == "val_axis_scale":
        val_axes = chart_el.findall("c:plotArea/c:valAx", NS)
        for ax in val_axes:
            scaling = ax.find("c:scaling", NS)
            if scaling is None:
                continue
            has_custom = any(
                ax.find(tag, NS) is not None
                for tag in ("c:scaling/c:min", "c:scaling/c:max", "c:majorUnit")
            )
            if has_custom:
                return True, ""
        return False, "세로(값) 축 눈금(최소값/최대값/주 단위)이 설정되지 않았습니다."

    if rule == "data_labels":
        for show_val in chart_el.findall(".//c:dLbls/c:showVal", NS):
            if show_val.attrib.get("val") == "1":
                return True, ""
        return False, "데이터 레이블 값이 표시되도록 설정되지 않았습니다."

    return False, "차트 세부 지시사항 확인에 실패했습니다."
