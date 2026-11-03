"""Read an uploaded Excel or CSV sheet into plain rows.

Real office sheets are untidy: a title line above the headings, blank rows,
trailing empty columns. This finds the real heading row and works from there.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import BinaryIO

from openpyxl import load_workbook

MAX_ROWS = 20000
SAMPLE_SIZE = 5


@dataclass
class SheetData:
    headers: list[str]
    rows: list[list[str]]
    sheet_name: str
    header_row_number: int
    # Columns that had a heading but no data anywhere.
    empty_columns: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def samples(self, column_index: int, limit: int = SAMPLE_SIZE) -> list[str]:
        """A few real values from one column, to show him what it contains."""
        found: list[str] = []
        for row in self.rows:
            if column_index >= len(row):
                continue
            value = row[column_index].strip()
            if value and value not in found:
                found.append(value)
            if len(found) >= limit:
                break
        return found


def _clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    # Dates and numbers come back as real Python objects; keep them readable.
    return str(value).strip()


def _looks_like_header(row: list[str]) -> bool:
    """A heading row has several short, non-numeric, non-empty cells."""
    filled = [c for c in row if c]
    if len(filled) < 3:
        return False
    numeric = sum(1 for c in filled if c.replace(".", "", 1).isdigit())
    if numeric > len(filled) / 2:
        return False
    return sum(1 for c in filled if len(c) <= 40) >= len(filled) - 1


def _find_header_row(raw: list[list[str]]) -> int:
    """Skip title lines and blanks. Returns the index of the heading row."""
    for index, row in enumerate(raw[:15]):
        if _looks_like_header(row):
            return index
    return 0


def _from_raw(raw: list[list[str]], sheet_name: str) -> SheetData:
    if not raw:
        raise ValueError("The file appears to be empty.")

    header_index = _find_header_row(raw)
    headers_raw = raw[header_index]

    # Drop trailing empty heading cells.
    while headers_raw and not headers_raw[-1]:
        headers_raw = headers_raw[:-1]
    if not headers_raw:
        raise ValueError("Could not find a row of column headings in this file.")

    headers = [h or f"Column {i + 1}" for i, h in enumerate(headers_raw)]

    rows: list[list[str]] = []
    for row in raw[header_index + 1 :]:
        trimmed = row[: len(headers)]
        trimmed += [""] * (len(headers) - len(trimmed))
        if any(cell for cell in trimmed):
            rows.append(trimmed)
        if len(rows) >= MAX_ROWS:
            break

    empty_columns = [
        headers[i]
        for i in range(len(headers))
        if not any(row[i] for row in rows)
    ]

    return SheetData(
        headers=headers,
        rows=rows,
        sheet_name=sheet_name,
        header_row_number=header_index + 1,
        empty_columns=empty_columns,
    )


def read_excel(stream: BinaryIO) -> SheetData:
    workbook = load_workbook(stream, read_only=True, data_only=True)
    sheet = workbook.active
    if sheet is None:
        raise ValueError("This workbook has no sheets.")
    raw = [[_clean(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]
    workbook.close()
    return _from_raw(raw, sheet.title)


def read_csv(stream: BinaryIO) -> SheetData:
    text = stream.read().decode("utf-8-sig", errors="replace")
    raw = [[_clean(cell) for cell in row] for row in csv.reader(io.StringIO(text))]
    return _from_raw(raw, "CSV")


def read_sheet(stream: BinaryIO, filename: str) -> SheetData:
    if filename.lower().endswith(".csv"):
        return read_csv(stream)
    return read_excel(stream)
