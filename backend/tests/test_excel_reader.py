"""Reading untidy sheets: title lines, blank rows, ragged columns."""

import io

import pytest
from openpyxl import Workbook

from app.services.excel_reader import read_csv, read_excel


def make_workbook(rows: list[list]) -> io.BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Widows List"
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def test_skips_a_title_line_above_the_headings():
    stream = make_workbook(
        [
            ["ZILA SAINIK BOARD - LIST OF WIDOWS"],
            [],
            ["S.No", "Name of Widow", "Mob No"],
            [1, "Sunita Devi", "9876543210"],
            [2, "Kamlesh Kaur", "9812345678"],
        ]
    )
    sheet = read_excel(stream)
    assert sheet.headers == ["S.No", "Name of Widow", "Mob No"]
    assert sheet.header_row_number == 3
    assert sheet.row_count == 2


def test_blank_rows_are_dropped():
    stream = make_workbook(
        [
            ["Name of Widow", "Mob No"],
            ["Sunita Devi", "9876543210"],
            [None, None],
            ["", ""],
            ["Kamlesh Kaur", "9812345678"],
        ]
    )
    assert read_excel(stream).row_count == 2


def test_short_rows_are_padded_not_dropped():
    stream = make_workbook(
        [
            ["Name of Widow", "Mob No", "Remarks"],
            ["Sunita Devi", "9876543210"],  # no remark
        ]
    )
    sheet = read_excel(stream)
    assert sheet.rows[0] == ["Sunita Devi", "9876543210", ""]


def test_samples_skip_blanks_and_repeats():
    stream = make_workbook(
        [
            ["Name of Widow", "State"],
            ["A", "Punjab"],
            ["B", ""],
            ["C", "Punjab"],
            ["D", "Haryana"],
        ]
    )
    sheet = read_excel(stream)
    assert sheet.samples(1) == ["Punjab", "Haryana"]


def test_columns_with_no_data_are_reported():
    stream = make_workbook(
        [
            ["Name of Widow", "Aadhaar"],
            ["Sunita Devi", ""],
            ["Kamlesh Kaur", ""],
        ]
    )
    assert read_excel(stream).empty_columns == ["Aadhaar"]


def test_empty_file_is_refused_with_a_reason():
    with pytest.raises(ValueError):
        read_excel(make_workbook([]))


def test_csv_is_read_the_same_way():
    csv_text = "S.No,Name of Widow,Mob No\n1,Sunita Devi,9876543210\n"
    sheet = read_csv(io.BytesIO(csv_text.encode("utf-8")))
    assert sheet.headers == ["S.No", "Name of Widow", "Mob No"]
    assert sheet.row_count == 1
