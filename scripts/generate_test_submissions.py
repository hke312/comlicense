"""Generate 5 realistic mock student .xlsm submission files under /test/ for grading verification."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.workbook.defined_name import DefinedName

from comlicense_grader.config import BASE_DIR, EXAMS_DIR
from comlicense_grader.grader.engine import get_engine

TEST_OUT_DIR = BASE_DIR / "test"
SAMPLE_XLSM = EXAMS_DIR / "sample_01" / "question.xlsm"
SAMPLE_SPEC = EXAMS_DIR / "sample_01" / "answer_spec.json"


def _apply_basic_1(wb: openpyxl.Workbook, spec: dict, *, typo_last_cell: bool = False) -> None:
    ws = wb["기본작업-1"]
    expected = spec["sections"]["basic"]["tasks"][0]["expected_cells"]
    for coord, val in expected.items():
        ws[coord].value = val
    if typo_last_cell:
        ws["F8"].value = "인기"  # 일부 오타 -> 기본작업-1 전부감점(0점) 테스트


def _apply_basic_2(wb: openpyxl.Workbook, items_to_solve: set[int]) -> None:
    ws = wb["기본작업-2"]
    if 1 in items_to_solve:
        ws.merge_cells("A1:F1")
        ws["A1"].font = Font(name="맑은 고딕", size=16, bold=True)
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

    if 2 in items_to_solve:
        header_fill = PatternFill(fill_type="solid", start_color="D9E1F2", end_color="D9E1F2")
        thin = Side(style="thin", color="000000")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for col in range(1, 7):
            ws.cell(3, col).fill = header_fill
        for row in range(3, 16):
            for col in range(1, 7):
                ws.cell(row, col).border = border

    if 3 in items_to_solve:
        for rng in ("A4:A6", "A7:A9", "A10:A12", "A13:A15"):
            ws.merge_cells(rng)
            top_left = rng.split(":")[0]
            ws[top_left].alignment = Alignment(horizontal="center", vertical="center")

    if 4 in items_to_solve:
        for r in range(4, 16):
            ws[f"D{r}"].number_format = "#,##0"
            ws[f"E{r}"].number_format = '0"kg"'
            ws[f"F{r}"].number_format = "₩#,##0"

    if 5 in items_to_solve:
        dn = DefinedName(name="총판매금액", attr_text="'기본작업-2'!$F$4:$F$15")
        wb.defined_names.add(dn)


def _apply_basic_3(wb: openpyxl.Workbook) -> None:
    ws = wb["기본작업-3"]
    # 고급 필터 추출 결과 영역(A22 이하) 예시 입력
    ws["A22"].value = "예약일자"
    ws["B22"].value = "이사일자"
    ws["C22"].value = "계약자명"
    ws["A23"].value = "2025-02-03"
    ws["B23"].value = "2025-03-07"
    ws["C23"].value = "김나경"
    ws["A24"].value = "2025-02-04"
    ws["B24"].value = "2025-03-04"
    ws["C24"].value = "임홍진"


def _apply_calc(wb: openpyxl.Workbook, solved_nums: set[int], *, hardcode_q1: bool = False) -> None:
    ws = wb["계산작업"]
    if 1 in solved_nums:
        for r in range(3, 11):
            ws[f"D{r}"].value = f"=C{r}+TIME(0,B{r}*6,0)"
    elif hardcode_q1:
        # 수식 없이 결과값만 직접 입력한 오답 사례
        ws["D3"].value = "08:36:00"

    if 2 in solved_nums:
        for r in range(3, 11):
            ws[f"J{r}"].value = f'=IF(I{r}>=5000,"우수","보통")'

    if 3 in solved_nums:
        ws["D24"].value = "=AVERAGE(D14,D16,D17,D18)"

    if 4 in solved_nums:
        for r in range(14, 25):
            ws[f"J{r}"].value = f"=RANDBETWEEN(H{r},I{r})"

    if 5 in solved_nums:
        for r in range(28, 38):
            ws[f"E{r}"].value = f'=IF(LEFT(B{r},1)="1","컴활1급",IF(LEFT(B{r},1)="2","컴활2급","워드프로세서"))'


def _apply_analysis(wb: openpyxl.Workbook, *, solve_1: bool, solve_2: bool, typo_2: bool = False) -> None:
    if solve_1:
        ws1 = wb["분석작업-1"]
        # E6 = B4*650000 - (B4*650000*0.7 + 15000000 + B4*55000) = B4*140000 - 15000000
        # Target E6 = 20,000,000 -> B4 = 250
        ws1["B4"].value = 250

    if solve_2:
        ws2 = wb["분석작업-2"]
        expected = {
            "G10": 12300, "H10": 14200, "I10": 14700,
            "G11": 9800,  "H11": 10400, "I11": 10700,
            "G12": 11600, "H12": 11800, "I12": 12200,
            "G13": 14000, "H13": 12790, "I13": 13300,
        }
        for coord, val in expected.items():
            ws2[coord].value = val
        if typo_2:
            ws2["I13"].value = 13000  # 1개 값 오류 -> 분석작업-2 전부감점 테스트


def _apply_macro_sheet_effects(wb: openpyxl.Workbook, *, solve_m1: bool, solve_m2: bool) -> None:
    ws = wb["매크로작업"]
    if solve_m1:
        for r in range(4, 14):
            ws[f"G{r}"].value = f"=SUM(B{r}:F{r})"
    if solve_m2:
        fill = PatternFill(fill_type="solid", start_color="FFF2CC", end_color="FFF2CC")
        font = Font(name="맑은 고딕", bold=True)
        for col in range(1, 8):
            cell = ws.cell(3, col)
            cell.fill = fill
            cell.font = font


def _patch_ooxml_zip(
    target_xlsm: Path,
    *,
    include_vba: bool,
    macro_button_count: int,
    chart_features: set[str],
) -> None:
    """Patch xl/charts/chart1.xml, xl/vbaProject.bin, and VML macro bindings inside the saved .xlsm."""
    with zipfile.ZipFile(SAMPLE_XLSM, "r") as src_z:
        orig_chart_xml = src_z.read("xl/charts/chart1.xml").decode("utf-8")

    # Apply chart modifications based on chart_features: {"title", "type", "legend", "axis", "labels"}
    chart_xml = orig_chart_xml
    if "title" in chart_features:
        title_block = (
            '<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/>'
            '<a:p><a:r><a:t>1분기 보드게임 매출 현황</a:t></a:r></a:p>'
            '</c:rich></c:tx><c:overlay val="0"/></c:title>'
            '<c:autoTitleDeleted val="0"/>'
        )
        chart_xml = chart_xml.replace('<c:autoTitleDeleted val="1"/>', title_block, 1)

    if "type" in chart_features:
        chart_xml = chart_xml.replace("<c:lineChart>", '<c:barChart><c:barDir val="col"/>', 1)
        chart_xml = chart_xml.replace("</c:lineChart>", "</c:barChart>", 1)

    if "legend" in chart_features:
        chart_xml = chart_xml.replace('<c:legendPos val="r"/>', '<c:legendPos val="b"/>', 1)

    if "axis" in chart_features:
        chart_xml = chart_xml.replace(
            '<c:valAx><c:axId val="548360304"/><c:scaling><c:orientation val="minMax"/></c:scaling>',
            '<c:valAx><c:axId val="548360304"/><c:scaling><c:orientation val="minMax"/>'
            '<c:min val="20000000"/><c:max val="45000000"/></c:scaling>',
            1,
        )
        chart_xml = chart_xml.replace(
            '<c:crossBetween val="between"/></c:valAx>',
            '<c:majorUnit val="5000000"/><c:crossBetween val="between"/></c:valAx>',
            1,
        )

    if "labels" in chart_features:
        chart_xml = chart_xml.replace('<c:showVal val="0"/>', '<c:showVal val="1"/>', 1)

    tmp_zip = target_xlsm.with_suffix(".tmp.xlsm")
    with zipfile.ZipFile(target_xlsm, "r") as zin, zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zout:
        existing_names = set(zin.namelist())
        for name in zin.namelist():
            if name == "xl/charts/chart1.xml":
                zout.writestr(name, chart_xml.encode("utf-8"))
            else:
                zout.writestr(name, zin.read(name))

        if "xl/charts/chart1.xml" not in existing_names:
            zout.writestr("xl/charts/chart1.xml", chart_xml.encode("utf-8"))

        if include_vba and "xl/vbaProject.bin" not in existing_names:
            zout.writestr("xl/vbaProject.bin", b"DUMMY_VBA_PROJECT_FOR_COMLICENSE_TEST")

        if macro_button_count > 0:
            macro_tags = "\n".join(
                f"<x:ClientData ObjectType=\"Button\"><x:FmlaMacro>Macro{i + 1}</x:FmlaMacro></x:ClientData>"
                for i in range(macro_button_count)
            )
            vml_content = f"<xml xmlns:x=\"urn:schemas-microsoft-com:office:excel\">\n{macro_tags}\n</xml>"
            zout.writestr("xl/drawings/vmlDrawing1.vml", vml_content.encode("utf-8"))

    tmp_zip.replace(target_xlsm)


def build_student_file(
    filename: str,
    spec: dict,
    *,
    b1: bool = False,
    b1_typo: bool = False,
    b2_items: set[int] | None = None,
    b3: bool = False,
    calc_nums: set[int] | None = None,
    calc_q1_hardcode: bool = False,
    a1: bool = False,
    a2: bool = False,
    a2_typo: bool = False,
    m1_effect: bool = False,
    m2_effect: bool = False,
    include_vba: bool = False,
    macro_buttons: int = 0,
    chart_features: set[str] | None = None,
) -> Path:
    TEST_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TEST_OUT_DIR / filename
    shutil.copy2(SAMPLE_XLSM, out_path)

    wb = openpyxl.load_workbook(out_path, keep_vba=True)
    if b1 or b1_typo:
        _apply_basic_1(wb, spec, typo_last_cell=b1_typo)
    if b2_items:
        _apply_basic_2(wb, b2_items)
    if b3:
        _apply_basic_3(wb)
    _apply_calc(wb, calc_nums or set(), hardcode_q1=calc_q1_hardcode)
    _apply_analysis(wb, solve_1=a1, solve_2=a2, typo_2=a2_typo)
    _apply_macro_sheet_effects(wb, solve_m1=m1_effect, solve_m2=m2_effect)
    wb.save(out_path)
    wb.close()

    _patch_ooxml_zip(
        out_path,
        include_vba=include_vba,
        macro_button_count=macro_buttons,
        chart_features=chart_features or set(),
    )
    return out_path


def main() -> None:
    spec = json.loads(SAMPLE_SPEC.read_text(encoding="utf-8"))
    students = [
        dict(
            filename="01_김만점_100점_합격.xlsm",
            b1=True,
            b2_items={1, 2, 3, 4, 5},
            b3=True,
            calc_nums={1, 2, 3, 4, 5},
            a1=True,
            a2=True,
            m1_effect=True,
            m2_effect=True,
            include_vba=True,
            macro_buttons=2,
            chart_features={"title", "type", "legend", "axis", "labels"},
        ),
        dict(
            filename="02_이우수_83점_합격.xlsm",
            b1=True,
            b2_items={1, 2, 3, 4},  # 8/10점 (이름정의 누락 -2)
            b3=True,
            calc_nums={1, 2, 3, 5},  # 32/40점 (4번 누락 -8)
            a1=True,
            a2=True,  # 20/20점
            m1_effect=True,
            m2_effect=False,
            include_vba=True,
            macro_buttons=1,  # 매크로1 5점
            chart_features={"title", "type", "legend", "axis"},  # 차트 4개 8점 -> 문제4=13점 -> 총 83점
        ),
        dict(
            filename="03_박합격_71점_합격.xlsm",
            b1=True,
            b2_items={1, 2, 3},  # 6/10점
            b3=False,  # 문제1 = 5+6+0 = 11점
            calc_nums={1, 3, 4, 5},  # 32/40점
            a1=True,
            a2=True,  # 20/20점
            m1_effect=False,
            m2_effect=False,
            include_vba=False,
            macro_buttons=0,
            chart_features={"title", "type", "legend", "axis"},  # 8점 -> 11+32+20+8 = 71점
        ),
        dict(
            filename="04_최아쉽_54점_불합격.xlsm",
            b1_typo=True,  # 1칸 오타 -> 0/5점 (전부감점 확인)
            b2_items={1, 2, 3, 4},  # 8/10점
            b3=True,  # 5/5점 -> 문제1 = 13점
            calc_nums={1, 3, 5},  # 24/40점
            a1=True,
            a2=True,
            a2_typo=True,  # 1개 셀 오류 -> 0/10점 -> 문제3 = 10점
            m1_effect=True,
            m2_effect=False,
            include_vba=True,
            macro_buttons=0,  # 매크로1 기록만 3점, 단추 미연결
            chart_features={"title", "type"},  # 4점 -> 문제4 = 7점 -> 총 54점
        ),
        dict(
            filename="05_정초보_23점_불합격.xlsm",
            b1=False,
            b2_items={1, 2, 3},  # 6/10점
            b3=False,  # 문제1 = 6점
            calc_nums={3},  # 8/40점
            calc_q1_hardcode=True,  # 1번 수식 없이 값만 입력 -> 0점 확인
            a1=False,
            a2=False,  # 문제3 = 0점
            m1_effect=True,
            m2_effect=False,
            include_vba=True,
            macro_buttons=1,  # 매크로1 5점
            chart_features={"title", "type"},  # 4점 -> 문제4 = 9점 -> 총 23점
        ),
    ]

    # Adjust student 2 macro/chart to hit 82 cleanly:
    # b1(5) + b2(8) + b3(5) = 18; calc(32); analysis(20); etc: macro1(5)+macro2_vba_only? Wait:
    # Actually let's check what score each gets!
    engine = get_engine()
    for cfg in students:
        p = build_student_file(spec=spec, **cfg)
        scores, deductions, _, threshold = engine.grade_file("sample_01", p)
        status = "합격" if scores.total >= threshold else "불합격"
        print(
            f"[{p.name}] 총점={scores.total}점 ({status}) | "
            f"문제1={scores.problem1}/20, 문제2={scores.problem2}/40, "
            f"문제3={scores.problem3}/20, 문제4={scores.problem4}/20 | "
            f"감점={len(deductions)}건"
        )


if __name__ == "__main__":
    main()
