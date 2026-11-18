"""Main grading engine orchestrating catalog resolution and 4-section scoring."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import openpyxl

from comlicense_grader.config import CATALOG_PATH, EXAMS_DIR
from comlicense_grader.grader.analysis_tasks import grade_analysis_tasks
from comlicense_grader.grader.base import WorkbookContext
from comlicense_grader.grader.basic_tasks import grade_basic_tasks
from comlicense_grader.grader.calc_tasks import grade_calc_tasks
from comlicense_grader.grader.etc_tasks import grade_etc_tasks
from comlicense_grader.models.schemas import DeductionItem, ExamInfo, SectionScores


class GradingEngine:
    """Loads exam specifications and evaluates submitted Excel workbooks."""

    def __init__(
        self,
        catalog_path: Path | None = None,
        exams_dir: Path | None = None,
    ) -> None:
        self.catalog_path: Path = catalog_path or CATALOG_PATH
        self.exams_dir: Path = exams_dir or EXAMS_DIR

    def load_catalog(self) -> list[ExamInfo]:
        """Load all exam entries from catalog.json."""
        if not self.catalog_path.exists():
            return []
        data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        exams: list[ExamInfo] = []
        for raw in data.get("exams", []):
            info = ExamInfo(**raw)
            q_path = self.exams_dir / info.question_file
            has_own = q_path.exists()
            has_fallback = bool(info.fallback_exam_id)
            info.available = has_own or has_fallback
            exams.append(info)
        return exams

    def get_exam(self, exam_id: str) -> ExamInfo:
        """Look up a single exam by exam_id or raise ValueError."""
        exams = self.load_catalog()
        for exam in exams:
            if exam.exam_id == exam_id:
                return exam
        raise ValueError(f"존재하지 않는 회차입니다: {exam_id}")

    def resolve_exam_files(self, exam_id: str) -> tuple[ExamInfo, Path, Path]:
        """Resolve (ExamInfo, question_xlsm_path, answer_spec_json_path) with fallback."""
        exams = {e.exam_id: e for e in self.load_catalog()}
        if exam_id not in exams:
            raise ValueError(f"존재하지 않는 회차입니다: {exam_id}")

        exam = exams[exam_id]
        question_path = self.exams_dir / exam.question_file
        spec_path = self.exams_dir / exam.answer_spec_file

        if (not question_path.exists() or not spec_path.exists()) and exam.fallback_exam_id:
            fb = exams.get(exam.fallback_exam_id)
            if fb is not None:
                if not question_path.exists():
                    question_path = self.exams_dir / fb.question_file
                if not spec_path.exists():
                    spec_path = self.exams_dir / fb.answer_spec_file

        if not question_path.exists():
            raise FileNotFoundError(f"문제 파일을 찾을 수 없습니다: {question_path}")
        if not spec_path.exists():
            raise FileNotFoundError(f"채점 기준 파일을 찾을 수 없습니다: {spec_path}")

        return exam, question_path, spec_path

    def resolve_problem_sheet(self, exam_id: str) -> tuple[ExamInfo, Path | None]:
        """Resolve optional problem_sheet.html path with fallback to fallback_exam_id."""
        exams = {e.exam_id: e for e in self.load_catalog()}
        if exam_id not in exams:
            raise ValueError(f"존재하지 않는 회차입니다: {exam_id}")

        exam = exams[exam_id]
        candidates: list[str] = []
        if exam.problem_sheet_file:
            candidates.append(exam.problem_sheet_file)
        if exam.fallback_exam_id and exam.fallback_exam_id in exams:
            fb = exams[exam.fallback_exam_id]
            if fb.problem_sheet_file:
                candidates.append(fb.problem_sheet_file)

        for rel_path in candidates:
            full_path = self.exams_dir / rel_path
            if full_path.exists():
                return exam, full_path
        return exam, None

    def load_answer_spec(self, spec_path: Path) -> dict[str, Any]:
        """Read answer_spec.json from disk."""
        return json.loads(spec_path.read_text(encoding="utf-8"))

    def grade_file(
        self, exam_id: str, file_path: Path
    ) -> tuple[SectionScores, list[DeductionItem], ExamInfo, int]:
        """Grade a submitted workbook against the resolved exam specification."""
        exam, _, spec_path = self.resolve_exam_files(exam_id)
        spec = self.load_answer_spec(spec_path)
        pass_threshold = int(spec.get("pass_threshold", 70))

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                zip_entries = {name: zf.read(name) for name in zf.namelist()}
        except zipfile.BadZipFile as exc:
            raise ValueError("올바른 엑셀(.xlsx/.xlsm) 파일이 아닙니다.") from exc

        wb_formulas = None
        wb_values = None
        try:
            wb_formulas = openpyxl.load_workbook(file_path, data_only=False)
            wb_values = openpyxl.load_workbook(file_path, data_only=True)
            ctx = WorkbookContext(
                wb_formulas=wb_formulas,
                wb_values=wb_values,
                zip_entries=zip_entries,
            )

            sections = spec.get("sections", {})
            r1 = grade_basic_tasks(ctx, sections.get("basic", {}))
            r2 = grade_calc_tasks(ctx, sections.get("calc", {}))
            r3 = grade_analysis_tasks(ctx, sections.get("analysis", {}))
            r4 = grade_etc_tasks(ctx, sections.get("etc", {}))

            total = r1.score + r2.score + r3.score + r4.score
            scores = SectionScores(
                problem1=r1.score,
                problem2=r2.score,
                problem3=r3.score,
                problem4=r4.score,
                total=total,
            )
            deductions = [*r1.deductions, *r2.deductions, *r3.deductions, *r4.deductions]
            return scores, deductions, exam, pass_threshold
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"엑셀 파일 분석 중 오류가 발생했습니다: {exc}") from exc
        finally:
            if wb_formulas is not None:
                wb_formulas.close()
            if wb_values is not None:
                wb_values.close()


_engine_instance: GradingEngine | None = None


def get_engine() -> GradingEngine:
    """Return a shared GradingEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = GradingEngine()
    return _engine_instance
