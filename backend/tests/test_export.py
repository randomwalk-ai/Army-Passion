"""Downloading a chatbot answer as an Excel file."""

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app
from app.services.export import answer_filename, build_answer_workbook


def test_dates_become_real_excel_dates():
    content = build_answer_workbook(
        "Children turning 18", ["Child", "Date of birth"],
        [["Ankit Kaur", "29-11-2008"], ["No date", None]],
    )
    sheet = load_workbook(BytesIO(content)).active
    assert sheet["A1"].value == "Child" and sheet["B1"].value == "Date of birth"
    assert sheet["B2"].value.date().isoformat() == "2008-11-29"
    assert sheet["B3"].value is None


def test_sheet_title_strips_characters_excel_forbids():
    content = build_answer_workbook("A/B: C*D?", ["X"], [[1]])
    sheet = load_workbook(BytesIO(content)).active
    assert all(ch not in sheet.title for ch in "[]:*?/\\")


def test_filename_is_safe_and_ends_in_xlsx():
    assert answer_filename('Families in "Moga"?').endswith(".xlsx")
    assert '"' not in answer_filename('Families in "Moga"?')


def test_api_export_roundtrip():
    client = TestClient(app)
    response = client.post(
        "/api/ask/export",
        json={"title": "Families in Moga", "columns": ["Name"], "rows": [["Ramesh"], ["Suresh"]]},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    sheet = load_workbook(BytesIO(response.content)).active
    assert [c.value for c in sheet["A"]] == ["Name", "Ramesh", "Suresh"]


def test_api_export_refuses_empty():
    client = TestClient(app)
    response = client.post("/api/ask/export", json={"title": "Nothing", "columns": [], "rows": []})
    assert response.status_code == 400
