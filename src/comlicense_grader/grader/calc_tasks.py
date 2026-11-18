"""Grader for Problem 2: 계산작업 (5 formula problems × 8 pts = 40 pts, no partial credit)."""

from __future__ import annotations

import datetime as dt
import math
import random
import re
from typing import Any

from openpyxl.utils import column_index_from_string, get_column_letter, range_boundaries
from openpyxl.worksheet.worksheet import Worksheet

from comlicense_grader.grader.base import (
    EXCEL_ERRORS,
    SectionResult,
    WorkbookContext,
    try_parse_time_fraction,
    values_match,
)
from comlicense_grader.models.schemas import DeductionItem

CELL_REF_RE = re.compile(r"(\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)")


def grade_calc_tasks(ctx: WorkbookContext, section_spec: dict[str, Any]) -> SectionResult:
    """Grade all 5 formula tasks in 계산작업 (each 8 pts, all-or-nothing)."""
    problem_no = int(section_spec.get("problem_no", 2))
    max_score = int(section_spec.get("max_score", 40))
    tasks = section_spec.get("tasks", [])

    earned = 0
    deductions: list[DeductionItem] = []

    for task in tasks:
        pts, item_deduction = _grade_single_calc_task(ctx, problem_no, task)
        earned += pts
        if item_deduction is not None:
            deductions.append(item_deduction)

    return SectionResult(
        problem_no=problem_no,
        score=min(earned, max_score),
        max_score=max_score,
        deductions=deductions,
    )


def _grade_single_calc_task(
    ctx: WorkbookContext, problem_no: int, task: dict[str, Any]
) -> tuple[int, DeductionItem | None]:
    sheet_name = task.get("sheet", "계산작업")
    task_name = task.get("task_name", "계산작업")
    max_pts = int(task.get("max_score", 8))
    require_formula = bool(task.get("require_formula", True))

    ws_f = ctx.get_sheet(sheet_name, values=False)
    ws_v = ctx.get_sheet(sheet_name, values=True)

    if ws_f is None:
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail=f"'{sheet_name}' 시트를 찾을 수 없습니다.",
        )

    mode = task.get("mode", "exact_cells")
    if mode == "exact_cells":
        targets: dict[str, Any] = task.get("targets", {})
        alt_targets: dict[str, Any] | None = task.get("alt_targets")
        tolerance = float(task.get("tolerance", 1e-4))
        cells = list(targets.keys())

        missing = _find_missing_formulas(ws_f, cells) if require_formula else []
        if missing:
            return 0, DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=max_pts,
                detail=f"수식 미입력 ({', '.join(missing[:3])})",
            )

        actuals = {c: _resolve_cell_value(ws_f, ws_v, c) for c in cells}
        err_cells = [c for c, v in actuals.items() if _is_error_value(v)]
        if err_cells:
            return 0, DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=max_pts,
                detail=f"수식 오류 발생 ({', '.join(err_cells[:3])})",
            )

        primary_ok = all(values_match(actuals[c], targets[c], tolerance) for c in cells)
        alt_ok = bool(
            alt_targets
            and all(values_match(actuals[c], alt_targets[c], tolerance) for c in cells)
        )
        if primary_ok or alt_ok:
            return max_pts, None

        bad = [c for c in cells if not values_match(actuals[c], targets[c], tolerance)]
        return 0, DeductionItem(
            problem_no=problem_no,
            task_name=task_name,
            deduction=max_pts,
            detail=f"계산 결과값 불일치 ({', '.join(bad[:3])})",
        )

    if mode == "non_empty_formula_values":
        cells = task.get("cells", [])
        missing = _find_missing_formulas(ws_f, cells) if require_formula else []
        if missing:
            return 0, DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=max_pts,
                detail=f"수식 미입력 ({', '.join(missing[:3])})",
            )

        for c in cells:
            val = _resolve_cell_value(ws_f, ws_v, c)
            if val is None or str(val).strip() == "" or _is_error_value(val):
                return 0, DeductionItem(
                    problem_no=problem_no,
                    task_name=task_name,
                    deduction=max_pts,
                    detail=f"수식 결과값이 비어 있거나 오류가 있습니다 ({c}).",
                )
        return max_pts, None

    if mode == "int_range":
        cells = task.get("cells", [])
        min_v = int(task.get("min_value", 1))
        max_v = int(task.get("max_value", 30))
        missing = _find_missing_formulas(ws_f, cells) if require_formula else []
        if missing:
            return 0, DeductionItem(
                problem_no=problem_no,
                task_name=task_name,
                deduction=max_pts,
                detail=f"수식 미입력 ({', '.join(missing[:3])})",
            )

        for c in cells:
            val = _resolve_cell_value(ws_f, ws_v, c)
            if _is_error_value(val) or val is None:
                return 0, DeductionItem(
                    problem_no=problem_no,
                    task_name=task_name,
                    deduction=max_pts,
                    detail=f"수식 결과 오류 또는 미계산 ({c})",
                )
            try:
                num = float(val)
            except (TypeError, ValueError):
                return 0, DeductionItem(
                    problem_no=problem_no,
                    task_name=task_name,
                    deduction=max_pts,
                    detail=f"정수 범위 결과 불일치 ({c})",
                )
            if not (min_v <= num <= max_v and abs(num - round(num)) < 1e-6):
                return 0, DeductionItem(
                    problem_no=problem_no,
                    task_name=task_name,
                    deduction=max_pts,
                    detail=f"범위({min_v}~{max_v}) 정수 불일치 ({c})",
                )
        return max_pts, None

    return 0, DeductionItem(
        problem_no=problem_no,
        task_name=task_name,
        deduction=max_pts,
        detail="알 수 없는 계산작업 채점 모드입니다.",
    )


def _find_missing_formulas(ws_f: Worksheet, cells: list[str]) -> list[str]:
    missing: list[str] = []
    for coord in cells:
        raw = ws_f[coord].value
        if not (isinstance(raw, str) and raw.strip().startswith("=")):
            missing.append(coord)
    return missing


def _is_error_value(val: Any) -> bool:
    return isinstance(val, str) and val.strip().upper() in EXCEL_ERRORS


def _resolve_cell_value(ws_f: Worksheet, ws_v: Worksheet | None, coord: str) -> Any:
    """Return Excel's cached value if present, otherwise evaluate common Excel formulas."""
    if ws_v is not None:
        cached = ws_v[coord].value
        if cached is not None:
            return cached
    raw = ws_f[coord].value
    if isinstance(raw, str) and raw.strip().startswith("="):
        return evaluate_excel_formula(ws_f, raw.strip(), visited=set())
    return raw


# ---------------------------------------------------------------------------
# Lightweight Safe Excel Formula Evaluator (Fallback when cached value is None)
# ---------------------------------------------------------------------------


def evaluate_excel_formula(
    ws: Worksheet, formula: str, visited: set[str] | None = None
) -> Any:
    """Safely evaluate basic 컴활 2급 Excel formulas without arbitrary code execution."""
    visited = visited or set()
    expr = formula.lstrip("=").strip()
    try:
        return _eval_expr(ws, expr, visited)
    except Exception:
        return None


def _get_cell_val(ws: Worksheet, coord: str, visited: set[str]) -> Any:
    clean = coord.replace("$", "").upper()
    if clean in visited:
        return None
    val = ws[clean].value
    if isinstance(val, str) and val.strip().startswith("="):
        return evaluate_excel_formula(ws, val.strip(), visited | {clean})
    return val


def _get_range_matrix(ws: Worksheet, rng: str, visited: set[str]) -> list[list[Any]]:
    clean = rng.replace("$", "").upper()
    min_c, min_r, max_c, max_r = range_boundaries(clean)
    matrix: list[list[Any]] = []
    for r in range(min_r, max_r + 1):
        row_vals: list[Any] = []
        for c in range(min_c, max_c + 1):
            coord = f"{get_column_letter(c)}{r}"
            row_vals.append(_get_cell_val(ws, coord, visited))
        matrix.append(row_vals)
    return matrix


def _flatten_args(ws: Worksheet, arg_strs: list[str], visited: set[str]) -> list[Any]:
    out: list[Any] = []
    for a in arg_strs:
        s = a.strip()
        if ":" in s and not s.startswith('"'):
            for row in _get_range_matrix(ws, s, visited):
                out.extend(row)
        else:
            out.append(_eval_expr(ws, s, visited))
    return out


def _to_num(val: Any) -> float:
    if val is None or val == "":
        return 0.0
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    if isinstance(val, (int, float)):
        return float(val)
    tf = try_parse_time_fraction(val)
    if tf is not None:
        return tf
    return float(str(val).replace(",", "").strip())


def _split_top_level_args(inner: str) -> list[str]:
    args: list[str] = []
    buf: list[str] = []
    depth = 0
    in_quotes = False
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == '"':
            in_quotes = not in_quotes
            buf.append(ch)
        elif not in_quotes:
            if ch == "(":
                depth += 1
                buf.append(ch)
            elif ch == ")":
                depth -= 1
                buf.append(ch)
            elif ch == "," and depth == 0:
                args.append("".join(buf).strip())
                buf = []
                i += 1
                continue
            else:
                buf.append(ch)
        else:
            buf.append(ch)
        i += 1
    if buf or args:
        args.append("".join(buf).strip())
    return args


def _eval_expr(ws: Worksheet, expr: str, visited: set[str]) -> Any:
    s = expr.strip()
    if not s:
        return ""
    if s.startswith('"') and s.endswith('"') and s.count('"') == 2:
        return s[1:-1]
    if s.upper() == "TRUE":
        return True
    if s.upper() == "FALSE":
        return False

    # Strip outer redundant parentheses
    if s.startswith("(") and _matching_paren(s, 0) == len(s) - 1:
        return _eval_expr(ws, s[1:-1], visited)

    # Check top-level comparison operators
    for op in ("<=", ">=", "<>", "=", "<", ">"):
        idx = _find_top_level_op(s, op)
        if idx != -1:
            left = _eval_expr(ws, s[:idx], visited)
            right = _eval_expr(ws, s[idx + len(op) :], visited)
            return _compare_values(left, right, op)

    # String concatenation &
    idx = _find_top_level_op(s, "&")
    if idx != -1:
        left = _eval_expr(ws, s[:idx], visited)
        right = _eval_expr(ws, s[idx + 1 :], visited)
        return f"{'' if left is None else left}{'' if right is None else right}"

    # Addition / subtraction (scan right-to-left)
    for op in ("+", "-"):
        idx = _find_top_level_op(s, op, reverse=True)
        if idx > 0:
            prev_ch = s[:idx].rstrip()[-1:]
            if prev_ch not in ("+", "-", "*", "/", "(", ","):
                lval = _to_num(_eval_expr(ws, s[:idx], visited))
                rval = _to_num(_eval_expr(ws, s[idx + 1 :], visited))
                return lval + rval if op == "+" else lval - rval

    # Multiplication / division
    for op in ("*", "/"):
        idx = _find_top_level_op(s, op, reverse=True)
        if idx > 0:
            lval = _to_num(_eval_expr(ws, s[:idx], visited))
            rval = _to_num(_eval_expr(ws, s[idx + 1 :], visited))
            if op == "/":
                return "#DIV/0!" if rval == 0 else lval / rval
            return lval * rval

    # Percentage literal
    if s.endswith("%"):
        return _to_num(_eval_expr(ws, s[:-1], visited)) / 100.0

    # Function call NAME(...)
    func_match = re.match(r"^([A-Z0-9_.]+)\((.*)\)$", s, re.IGNORECASE | re.DOTALL)
    if func_match:
        fname = func_match.group(1).upper()
        inner = func_match.group(2)
        args = _split_top_level_args(inner) if inner.strip() else []
        return _eval_function(ws, fname, args, visited)

    # Single cell reference
    if re.fullmatch(r"\$?[A-Z]{1,3}\$?\d+", s, re.IGNORECASE):
        return _get_cell_val(ws, s, visited)

    # Numeric literal
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return s


def _matching_paren(s: str, start: int) -> int:
    depth = 0
    in_quotes = False
    for i in range(start, len(s)):
        ch = s[i]
        if ch == '"':
            in_quotes = not in_quotes
        elif not in_quotes:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
    return -1


def _find_top_level_op(s: str, op: str, reverse: bool = False) -> int:
    depth = 0
    in_quotes = False
    indices = range(len(s) - len(op), -1, -1) if reverse else range(len(s) - len(op) + 1)
    for i in indices:
        ch = s[i]
        if ch == '"':
            in_quotes = not in_quotes
            continue
        if in_quotes:
            continue
        if ch == ")":
            depth += 1 if reverse else -1
            continue
        if ch == "(":
            depth += -1 if reverse else 1
            continue
        if depth == 0 and s[i : i + len(op)] == op:
            if op in ("<", ">", "=") and (
                (i > 0 and s[i - 1] in ("<", ">")) or s[i : i + 2] in ("<=", ">=", "<>")
            ):
                continue
            return i
    return -1


def _compare_values(left: Any, right: Any, op: str) -> bool:
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        try:
            lv = _to_num(left)
            rv = _to_num(right)
            if op == "=":
                return abs(lv - rv) < 1e-9
            if op == "<>":
                return abs(lv - rv) >= 1e-9
            if op == "<":
                return lv < rv
            if op == ">":
                return lv > rv
            if op == "<=":
                return lv <= rv
            if op == ">=":
                return lv >= rv
        except (TypeError, ValueError):
            pass
    ls = "" if left is None else str(left).strip()
    rs = "" if right is None else str(right).strip()
    if op == "=":
        return ls.casefold() == rs.casefold()
    if op == "<>":
        return ls.casefold() != rs.casefold()
    if op == "<":
        return ls < rs
    if op == ">":
        return ls > rs
    if op == "<=":
        return ls <= rs
    if op == ">=":
        return ls >= rs
    return False


def _eval_function(ws: Worksheet, fname: str, args: list[str], visited: set[str]) -> Any:
    if fname == "SUM":
        nums = [_to_num(v) for v in _flatten_args(ws, args, visited) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return sum(nums)
    if fname == "AVERAGE":
        nums = [_to_num(v) for v in _flatten_args(ws, args, visited) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return sum(nums) / len(nums) if nums else "#DIV/0!"
    if fname == "MAX":
        nums = [_to_num(v) for v in _flatten_args(ws, args, visited) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return max(nums) if nums else 0
    if fname == "MIN":
        nums = [_to_num(v) for v in _flatten_args(ws, args, visited) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return min(nums) if nums else 0
    if fname == "COUNT":
        return sum(1 for v in _flatten_args(ws, args, visited) if isinstance(v, (int, float)) and not isinstance(v, bool))
    if fname == "COUNTA":
        return sum(1 for v in _flatten_args(ws, args, visited) if v is not None and str(v) != "")
    if fname == "IF":
        cond = bool(_eval_expr(ws, args[0], visited))
        if cond:
            return _eval_expr(ws, args[1], visited) if len(args) > 1 else True
        return _eval_expr(ws, args[2], visited) if len(args) > 2 else False
    if fname == "AND":
        return all(bool(_eval_expr(ws, a, visited)) for a in args)
    if fname == "OR":
        return any(bool(_eval_expr(ws, a, visited)) for a in args)
    if fname == "NOT":
        return not bool(_eval_expr(ws, args[0], visited))
    if fname == "TIME":
        h = int(_to_num(_eval_expr(ws, args[0], visited)))
        m = int(_to_num(_eval_expr(ws, args[1], visited)))
        sec = int(_to_num(_eval_expr(ws, args[2], visited)))
        total_sec = (h * 3600 + m * 60 + sec) % 86400
        return total_sec / 86400.0
    if fname == "HOUR":
        tf = try_parse_time_fraction(_eval_expr(ws, args[0], visited)) or 0.0
        return int(round(tf * 86400)) // 3600 % 24
    if fname == "MINUTE":
        tf = try_parse_time_fraction(_eval_expr(ws, args[0], visited)) or 0.0
        return (int(round(tf * 86400)) % 3600) // 60
    if fname == "SECOND":
        tf = try_parse_time_fraction(_eval_expr(ws, args[0], visited)) or 0.0
        return int(round(tf * 86400)) % 60
    if fname == "LEFT":
        text = str(_eval_expr(ws, args[0], visited) or "")
        n = int(_to_num(_eval_expr(ws, args[1], visited))) if len(args) > 1 else 1
        return text[:n]
    if fname == "RIGHT":
        text = str(_eval_expr(ws, args[0], visited) or "")
        n = int(_to_num(_eval_expr(ws, args[1], visited))) if len(args) > 1 else 1
        return text[-n:] if n > 0 else ""
    if fname == "MID":
        text = str(_eval_expr(ws, args[0], visited) or "")
        start = int(_to_num(_eval_expr(ws, args[1], visited)))
        n = int(_to_num(_eval_expr(ws, args[2], visited)))
        return text[max(0, start - 1) : max(0, start - 1) + n]
    if fname == "LEN":
        return len(str(_eval_expr(ws, args[0], visited) or ""))
    if fname == "INT":
        return math.floor(_to_num(_eval_expr(ws, args[0], visited)))
    if fname == "MOD":
        a = _to_num(_eval_expr(ws, args[0], visited))
        b = _to_num(_eval_expr(ws, args[1], visited))
        return a % b
    if fname == "ROUND":
        a = _to_num(_eval_expr(ws, args[0], visited))
        d = int(_to_num(_eval_expr(ws, args[1], visited)))
        return round(a, d)
    if fname == "RANDBETWEEN":
        lo = int(_to_num(_eval_expr(ws, args[0], visited)))
        hi = int(_to_num(_eval_expr(ws, args[1], visited)))
        return random.randint(lo, hi)
    if fname == "RAND":
        return random.random()
    if fname == "CHOOSE":
        idx = int(_to_num(_eval_expr(ws, args[0], visited)))
        if 1 <= idx < len(args):
            return _eval_expr(ws, args[idx], visited)
        return "#VALUE!"
    if fname in ("RANK", "RANK.EQ"):
        target = _to_num(_eval_expr(ws, args[0], visited))
        vals = [_to_num(v) for v in _flatten_args(ws, [args[1]], visited) if isinstance(v, (int, float))]
        order = int(_to_num(_eval_expr(ws, args[2], visited))) if len(args) > 2 else 0
        sorted_vals = sorted(vals, reverse=(order == 0))
        return sorted_vals.index(target) + 1
    if fname in ("AVERAGEIF", "SUMIF", "COUNTIF"):
        rng_vals = _flatten_args(ws, [args[0]], visited)
        crit = _eval_expr(ws, args[1], visited)
        target_vals = _flatten_args(ws, [args[2]], visited) if len(args) > 2 else rng_vals
        matched = [
            target_vals[i]
            for i, v in enumerate(rng_vals)
            if i < len(target_vals) and _match_criteria(v, crit)
        ]
        if fname == "COUNTIF":
            return len(matched)
        nums = [_to_num(v) for v in matched if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if fname == "SUMIF":
            return sum(nums)
        return sum(nums) / len(nums) if nums else "#DIV/0!"
    if fname in ("DAVERAGE", "DSUM", "DCOUNT"):
        db_matrix = _get_range_matrix(ws, args[0].strip(), visited)
        field_arg = _eval_expr(ws, args[1], visited)
        crit_matrix = _get_range_matrix(ws, args[2].strip(), visited)
        if not db_matrix or not crit_matrix:
            return "#VALUE!"
        headers = [str(h).strip() if h is not None else "" for h in db_matrix[0]]
        if isinstance(field_arg, (int, float)):
            col_idx = int(field_arg) - 1
        else:
            col_idx = headers.index(str(field_arg).strip())
        crit_headers = [str(h).strip() if h is not None else "" for h in crit_matrix[0]]
        matched_vals: list[Any] = []
        for row in db_matrix[1:]:
            if _row_matches_d_criteria(row, headers, crit_matrix[1:], crit_headers):
                matched_vals.append(row[col_idx])
        nums = [_to_num(v) for v in matched_vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if fname == "DCOUNT":
            return len(nums)
        if fname == "DSUM":
            return sum(nums)
        return sum(nums) / len(nums) if nums else "#DIV/0!"
    if fname in ("VLOOKUP", "HLOOKUP"):
        key = _eval_expr(ws, args[0], visited)
        tbl = _get_range_matrix(ws, args[1].strip(), visited)
        idx = int(_to_num(_eval_expr(ws, args[2], visited))) - 1
        if fname == "VLOOKUP":
            for row in tbl:
                if values_match(row[0], key):
                    return row[idx] if 0 <= idx < len(row) else "#REF!"
        else:
            for c_idx, cell_val in enumerate(tbl[0]):
                if values_match(cell_val, key):
                    return tbl[idx][c_idx] if 0 <= idx < len(tbl) else "#REF!"
        return "#N/A"
    if fname == "INDEX":
        tbl = _get_range_matrix(ws, args[0].strip(), visited)
        r_idx = int(_to_num(_eval_expr(ws, args[1], visited))) - 1
        c_idx = int(_to_num(_eval_expr(ws, args[2], visited))) - 1 if len(args) > 2 else 0
        return tbl[r_idx][c_idx]
    if fname == "MATCH":
        key = _eval_expr(ws, args[0], visited)
        arr = _flatten_args(ws, [args[1]], visited)
        for idx, v in enumerate(arr):
            if values_match(v, key):
                return idx + 1
        return "#N/A"
    return None


def _match_criteria(val: Any, crit: Any) -> bool:
    if isinstance(crit, str):
        c = crit.strip()
        for op in ("<=", ">=", "<>", "<", ">", "="):
            if c.startswith(op):
                rhs = c[len(op) :].strip()
                try:
                    return _compare_values(val, float(rhs), op)
                except ValueError:
                    return _compare_values(val, rhs, op)
    return values_match(val, crit)


def _row_matches_d_criteria(
    row: list[Any],
    headers: list[str],
    crit_rows: list[list[Any]],
    crit_headers: list[str],
) -> bool:
    for crow in crit_rows:
        if all(v is None or str(v).strip() == "" for v in crow):
            continue
        row_ok = True
        for c_idx, ch in enumerate(crit_headers):
            cval = crow[c_idx] if c_idx < len(crow) else None
            if cval is None or str(cval).strip() == "":
                continue
            if ch not in headers:
                row_ok = False
                break
            col_idx = headers.index(ch)
            if not _match_criteria(row[col_idx], cval):
                row_ok = False
                break
        if row_ok:
            return True
    return False
