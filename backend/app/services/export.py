"""Turning a chatbot answer (already shown on screen) into a downloadable
Excel file, so the colonel can share a list with his officers or print it.

Builds the file from the title/columns/rows the screen already has — it
never re-runs a search, so this works for every kind of table answer
(a typed question, a suggestion, CEA, or a family's details).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

MAX_SHEET_TITLE = 31  # Excel's own limit


def _sheet_title(title: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", " ", title).strip() or "Answer"
    return cleaned[:MAX_SHEET_TITLE]


def _cell_value(value: Any):
    """DD-MM-YYYY text from the screen becomes a real Excel date, so it sorts
    and filters properly; everything else is written as-is."""
    if isinstance(value, str):
        m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", value)
        if m:
            d, mo, y = (int(x) for x in m.groups())
            try:
                return date(y, mo, d)
            except ValueError:
                return value
        m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4}) (\d{2}):(\d{2})", value)
        if m:
            d, mo, y, h, mi = (int(x) for x in m.groups())
            try:
                return datetime(y, mo, d, h, mi)
            except ValueError:
                return value
    return value


def build_answer_workbook(title: str, columns: list[str], rows: list[list[Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = _sheet_title(title)

    sheet.append(columns)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([_cell_value(v) for v in row])
    for cell in sheet[1]:
        cell.number_format = "@"  # headers stay plain text even if a header looks like a date

    for i, column in enumerate(columns, start=1):
        width = max(len(str(column)), *(len(str(r[i - 1])) for r in rows)) if rows else len(column)
        sheet.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 40)
    sheet.freeze_panes = "A2"

    from io import BytesIO

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def answer_filename(title: str) -> str:
    cleaned = re.sub(r"[^\w .-]", "", title).strip() or "Answer"
    return f"{cleaned[:80]}.xlsx"
