"""Shared workbook context, XML utilities, and value comparison helpers."""

from __future__ import annotations

import datetime as dt
import posixpath
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.worksheet.worksheet import Worksheet

from comlicense_grader.models.schemas import DeductionItem

EXCEL_ERRORS: frozenset[str] = frozenset(
    {"#VALUE!", "#NAME?", "#REF!", "#DIV/0!", "#N/A", "#NUM!", "#NULL!"}
)

NS: dict[str, str] = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


@dataclass
class SectionResult:
    """Result returned by a section grader."""

    problem_no: int
    score: int
    max_score: int
    deductions: list[DeductionItem] = field(default_factory=list)


@dataclass
class WorkbookContext:
    """Container holding formula/value workbooks and raw OOXML ZIP entries."""

    wb_formulas: Workbook
    wb_values: Workbook
    zip_entries: dict[str, bytes]

    def get_sheet(self, name: str, values: bool = False) -> Worksheet | None:
        """Return worksheet by exact name or whitespace-trimmed fallback."""
        wb = self.wb_values if values else self.wb_formulas
        if name in wb.sheetnames:
            return wb[name]
        stripped = name.replace(" ", "")
        for sname in wb.sheetnames:
            if sname.replace(" ", "") == stripped:
                return wb[sname]
        return None

    def read_xml(self, entry_name: str) -> ET.Element | None:
        """Parse an XML entry inside the workbook archive."""
        raw = self.zip_entries.get(entry_name)
        if not raw:
            return None
        try:
            return ET.fromstring(raw)
        except ET.ParseError:
            return None

    def list_zip(self, prefix: str, suffix: str = "") -> list[str]:
        """List ZIP entry paths matching prefix and suffix."""
        return sorted(
            name
            for name in self.zip_entries
            if name.startswith(prefix) and name.endswith(suffix)
        )

    def _resolve_target(self, base_dir: str, target: str) -> str:
        if target.startswith("/"):
            return target.lstrip("/")
        return posixpath.normpath(posixpath.join(base_dir, target))

    def get_sheet_xml_path(self, sheet_name: str) -> str | None:
        """Resolve worksheet XML path (e.g., xl/worksheets/sheet7.xml) for a sheet name."""
        wb_xml = self.read_xml("xl/workbook.xml")
        wb_rels = self.read_xml("xl/_rels/workbook.xml.rels")
        if wb_xml is None or wb_rels is None:
            return None

        rid: str | None = None
        for sheet_el in wb_xml.findall(".//main:sheet", NS):
            name = sheet_el.attrib.get("name", "")
            if name == sheet_name or name.replace(" ", "") == sheet_name.replace(" ", ""):
                rid = sheet_el.attrib.get(f"{{{NS['r']}}}id")
                break
        if not rid:
            return None

        for rel_el in wb_rels.findall(".//rel:Relationship", NS):
            if rel_el.attrib.get("Id") == rid:
                target = rel_el.attrib.get("Target", "")
                return self._resolve_target("xl", target)
        return None

    def get_sheet_drawing_paths(self, sheet_name: str) -> list[str]:
        """Return drawing XML paths linked to the given worksheet."""
        sheet_path = self.get_sheet_xml_path(sheet_name)
        if not sheet_path:
            return []
        sheet_dir = posixpath.dirname(sheet_path)
        sheet_file = posixpath.basename(sheet_path)
        rels_path = posixpath.join(sheet_dir, "_rels", f"{sheet_file}.rels")
        rels_xml = self.read_xml(rels_path)
        if rels_xml is None:
            return []

        drawings: list[str] = []
        for rel_el in rels_xml.findall(".//rel:Relationship", NS):
            rtype = rel_el.attrib.get("Type", "")
            target = rel_el.attrib.get("Target", "")
            if rtype.endswith("/drawing") or "drawing" in target:
                resolved = self._resolve_target(sheet_dir, target)
                if resolved in self.zip_entries:
                    drawings.append(resolved)
        return drawings

    def get_sheet_chart_paths(self, sheet_name: str) -> list[str]:
        """Return chart XML paths linked to the given worksheet via its drawings."""
        charts: list[str] = []
        for drawing_path in self.get_sheet_drawing_paths(sheet_name):
            d_dir = posixpath.dirname(drawing_path)
            d_file = posixpath.basename(drawing_path)
            d_rels_path = posixpath.join(d_dir, "_rels", f"{d_file}.rels")
            d_rels_xml = self.read_xml(d_rels_path)
            if d_rels_xml is None:
                continue
            for rel_el in d_rels_xml.findall(".//rel:Relationship", NS):
                rtype = rel_el.attrib.get("Type", "")
                target = rel_el.attrib.get("Target", "")
                if rtype.endswith("/chart") or "charts/chart" in target:
                    resolved = self._resolve_target(d_dir, target)
                    if resolved in self.zip_entries and resolved not in charts:
                        charts.append(resolved)
        return charts


def iter_range_coords(cell_range: str) -> list[str]:
    """Expand an A1-style range like 'D4:D15' into individual coordinate strings."""
    min_col, min_row, max_col, max_row = range_boundaries(cell_range)
    coords: list[str] = []
    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            coords.append(f"{get_column_letter(c)}{r}")
    return coords


def normalize_text(value: Any) -> str:
    """Normalize a cell value for case/whitespace-insensitive string comparison."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def try_parse_time_fraction(value: Any) -> float | None:
    """Convert time/datetime/HH:MM(:SS) string/serial float to Excel day fraction (0..1)."""
    if isinstance(value, dt.datetime):
        t = value.time()
        return (t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6) / 86400.0
    if isinstance(value, dt.time):
        return (value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1e6) / 86400.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) % 1.0 if float(value) >= 0 else None
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed = dt.datetime.strptime(text, fmt).time()
                return (parsed.hour * 3600 + parsed.minute * 60 + parsed.second) / 86400.0
            except ValueError:
                continue
    return None


def values_match(actual: Any, expected: Any, tolerance: float = 1e-4) -> bool:
    """Compare actual cell value against expected value with numeric and time support."""
    if actual is None:
        return False
    if isinstance(actual, str) and actual.strip().upper() in EXCEL_ERRORS:
        return False

    # Time comparison if expected looks like HH:MM:SS or datetime.time
    if isinstance(expected, str) and ":" in expected:
        exp_t = try_parse_time_fraction(expected)
        act_t = try_parse_time_fraction(actual)
        if exp_t is not None and act_t is not None:
            return abs(act_t - exp_t) <= tolerance

    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if isinstance(actual, (int, float)) and not isinstance(actual, bool):
            return abs(float(actual) - float(expected)) <= tolerance
        try:
            return abs(float(str(actual).replace(",", "").strip()) - float(expected)) <= tolerance
        except (ValueError, TypeError):
            return False

    return normalize_text(actual).casefold() == normalize_text(expected).casefold()
