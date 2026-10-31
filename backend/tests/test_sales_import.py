import io
import zipfile
from datetime import date, datetime, timedelta

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from app.auth.models import Role
from app.masterdata.models import Product
from app.safe_csv import neutralise, to_csv
from app.sales import parser
from app.sales.models import ImportRun, SalesRecord

HEADER = "date,product_code,quantity,region\n"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def planner(login_as):
    return login_as(Role.DEMAND_PLANNER)


@pytest.fixture
def product(db):
    item = Product(code="P001", name="Chair", unit="piece")
    db.add(item)
    db.commit()
    return item


def upload(client, content, name="sales.csv", kind="text/csv"):
    if isinstance(content, str):
        content = content.encode()
    return client.post("/api/imports/sales", files={"file": (name, content, kind)})


def xlsx_bytes(rows):
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def stored(db):
    db.expire_all()
    return db.scalars(select(SalesRecord).order_by(SalesRecord.period)).all()


# TC-Data-01: valid rows stored, bad rows reported, re-imports do not duplicate


def test_valid_rows_are_stored(client, planner, product, db):
    body = HEADER + "2025-01-01,P001,120,South\n2025-02-01,p001,130,South\n"
    response = upload(client, body)
    assert response.status_code == 200
    result = response.json()
    assert (result["imported"], result["updated"], result["rejected"]) == (2, 0, 0)
    assert [(r.period, r.quantity, r.region) for r in stored(db)] == [
        (date(2025, 1, 1), 120, "South"), (date(2025, 2, 1), 130, "South")]


def test_region_is_optional(client, planner, product, db):
    assert upload(client, "date,product_code,quantity\n2025-01-01,P001,5\n").status_code == 200
    assert stored(db)[0].region == ""


def test_column_names_ignore_case_and_order(client, planner, product, db):
    upload(client, " Quantity ,PRODUCT_CODE,Date\n7,P001,2025-01-01\n")
    assert stored(db)[0].quantity == 7


def test_excel_byte_order_mark_is_accepted(client, planner, product, db):
    upload(client, ("﻿" + HEADER + "2025-01-01,P001,5,\n").encode("utf-8"))
    assert stored(db)[0].quantity == 5


def test_blank_rows_are_skipped(client, planner, product, db):
    result = upload(client, HEADER + "\n2025-01-01,P001,5,\n,,,\n").json()
    assert (result["imported"], result["rejected"]) == (1, 0)


def test_100_valid_and_5_invalid_rows(client, planner, product, db):
    start = date(2020, 1, 1)
    good = [f"{start + timedelta(days=i)},P001,{i}," for i in range(100)]
    bad = ["2025-01-01,NOPE,1,", "01/02/2025,P001,1,", "2025-01-02,P001,-1,",
           "2025-01-03,P001,abc,", "2025-01-04,P001,1.5,"]
    result = upload(client, HEADER + "\n".join(good + bad) + "\n").json()
    assert (result["imported"], result["rejected"]) == (100, 5)
    assert [e["row"] for e in result["errors"]] == [102, 103, 104, 105, 106]
    assert [e["field"] for e in result["errors"]] == [
        "product_code", "date", "quantity", "quantity", "quantity"]
    assert len(stored(db)) == 100


def test_reimporting_updates_instead_of_duplicating(client, planner, product, db):
    upload(client, HEADER + "2025-01-01,P001,100,\n2025-02-01,P001,200,\n")
    result = upload(client, HEADER + "2025-01-01,P001,150,\n2025-03-01,P001,300,\n").json()
    assert (result["imported"], result["updated"]) == (1, 1)
    assert [r.quantity for r in stored(db)] == [150, 200, 300]


def test_same_period_in_two_regions_is_two_records(client, planner, product, db):
    result = upload(client, HEADER + "2025-01-01,P001,1,North\n2025-01-01,P001,2,South\n").json()
    assert (result["imported"], result["rejected"]) == (2, 0)


def test_duplicate_row_in_one_file_is_rejected(client, planner, product, db):
    result = upload(client, HEADER + "2025-01-01,P001,1,\n2025-01-01,P001,2,\n").json()
    assert (result["imported"], result["rejected"]) == (1, 1)
    assert "Duplicate" in result["errors"][0]["message"]
    assert stored(db)[0].quantity == 1


@pytest.mark.parametrize("line,field", [
    (",P001,1,", "date"),
    ("2025-13-01,P001,1,", "date"),
    ("2025-01-01,,1,", "product_code"),
    ("2025-01-01,P001,,", "quantity"),
    ("2025-01-01,P001,nan,", "quantity"),
    ("2025-01-01,P001,inf,", "quantity"),
    ("2025-01-01,P001,99999999999,", "quantity"),
    (f"2025-01-01,P001,1,{'x' * 61}", "region"),
])
def test_bad_values_are_reported(client, planner, product, db, line, field):
    result = upload(client, HEADER + line + "\n").json()
    assert result["rejected"] == 1 and result["errors"][0]["field"] == field
    assert stored(db) == []


def test_future_date_is_rejected(client, planner, product):
    tomorrow = date.today() + timedelta(days=1)
    result = upload(client, HEADER + f"{tomorrow},P001,1,\n").json()
    assert result["errors"][0]["message"] == "Date cannot be in the future"


def test_stored_errors_are_capped_but_the_count_stays_exact(client, planner, product, monkeypatch):
    monkeypatch.setattr("app.sales.service.MAX_STORED_ERRORS", 2)
    result = upload(client, HEADER + "bad,P001,1,\n" * 5).json()
    assert result["rejected"] == 5 and len(result["errors"]) == 2


def test_import_run_records_who_sent_it(client, planner, product, db):
    upload(client, HEADER + "2025-01-01,P001,1,\n")
    assert db.scalar(select(ImportRun.user_id)) == planner.id


# Excel files


def test_xlsx_with_real_dates_and_numbers(client, planner, product, db):
    content = xlsx_bytes([["Date", "Product_Code", "Quantity"],
                          [datetime(2025, 1, 1), "P001", 12.0],
                          [date(2025, 2, 1), "P001", 13]])
    result = upload(client, content, "sales.xlsx", XLSX).json()
    assert (result["imported"], result["rejected"]) == (2, 0)
    assert [r.quantity for r in stored(db)] == [12, 13]


def test_xlsx_with_bad_rows(client, planner, product):
    content = xlsx_bytes([["date", "product_code", "quantity"], ["nope", "P001", 1]])
    result = upload(client, content, "sales.xlsx", XLSX).json()
    assert result["errors"][0] == {
        "row": 2, "field": "date", "message": "Date must be in the format YYYY-MM-DD"}


# TC-Sec-04: malicious and malformed files


@pytest.mark.parametrize("name,content", [
    ("virus.exe", b"MZ\x00\x01"),
    ("macro.xlsm", b"PK"),
    ("old.xls", b"\xd0\xcf\x11\xe0"),
    ("no_extension", b"date,product_code,quantity\n"),
    ("renamed.csv", b"MZ\x90\x00\x03\x00"),
    ("latin1.csv", "date,product_code,quantity\n2025-01-01,caf\xe9,1\n".encode("latin-1")),
    ("renamed.xlsx", b"MZ\x90\x00\x03\x00"),
])
def test_wrong_file_types_are_rejected(client, planner, product, db, name, content):
    assert upload(client, content, name).status_code == 415
    assert stored(db) == []


def zip_with(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return output.getvalue()


def test_plain_zip_renamed_to_xlsx_is_rejected(client, planner):
    assert upload(client, zip_with({"a.txt": "hello"}), "a.xlsx").status_code == 415


def test_broken_workbook_is_rejected(client, planner):
    assert upload(client, zip_with({"xl/workbook.xml": "not xml"}), "a.xlsx").status_code == 415


def test_workbook_with_macros_is_rejected(client, planner):
    content = zip_with({"xl/workbook.xml": "<x/>", "xl/vbaProject.bin": "code"})
    response = upload(client, content, "a.xlsx")
    assert response.status_code == 415
    assert "macros" in response.json()["error"]["message"]


def test_oversized_when_unpacked_is_rejected(client, planner, monkeypatch):
    monkeypatch.setattr(parser, "MAX_UNZIPPED_BYTES", 10)
    content = zip_with({"xl/workbook.xml": "x" * 100})
    assert upload(client, content, "a.xlsx").status_code == 415


def test_file_over_10_mb_is_rejected(client, planner, monkeypatch):
    monkeypatch.setattr(parser, "MAX_UPLOAD_BYTES", 10)
    assert upload(client, HEADER).status_code == 413


@pytest.mark.parametrize("content", ["", "\n\n", "date,product_code\n2025-01-01,P001\n", HEADER])
def test_bad_layout_is_rejected(client, planner, content):
    assert upload(client, content).status_code == 400


def test_upload_without_a_file_is_rejected(client, planner):
    assert client.post("/api/imports/sales").status_code == 400


def test_failed_commit_is_reported_as_a_conflict(client, planner, product, db, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    def clash(self):
        raise IntegrityError("INSERT", {}, Exception("duplicate"))

    monkeypatch.setattr(Session, "commit", clash)
    assert upload(client, HEADER + "2025-01-01,P001,1,\n").status_code == 409


# Error report


def test_error_report_downloads_as_csv(client, planner, product):
    run = upload(client, HEADER + "2025-01-01,NOPE,1,\n").json()
    response = client.get(f"/api/imports/{run['id']}/errors.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text == "row,field,message\n2,product_code,Unknown product: NOPE\n"


def test_error_report_for_unknown_import_returns_404(client, planner):
    assert client.get("/api/imports/999/errors.csv").status_code == 404


def test_formula_in_a_bad_code_opens_as_text(client, planner, product):
    run = upload(client, HEADER + '2025-01-01,"=CMD()",1,\n').json()
    report = client.get(f"/api/imports/{run['id']}/errors.csv").text
    assert "=CMD()" in report  # shown, but inside a message that starts with plain text
    assert "\n2,product_code,Unknown" in report


@pytest.mark.parametrize("value", ["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"])
def test_spreadsheet_formulas_are_neutralised(value):
    assert neutralise(value) == "'" + value


def test_safe_values_are_unchanged():
    assert neutralise("Chair") == "Chair"
    assert neutralise(-5) == -5
    assert to_csv(["a"], [["=1"]]) == "a\n'=1\n"


# TC-Sec-03: access


@pytest.mark.parametrize("role", [r for r in Role if r is not Role.DEMAND_PLANNER])
def test_only_planners_can_import(client, login_as, product, db, role):
    login_as(role)
    assert upload(client, HEADER + "2025-01-01,P001,1,\n").status_code == 403
    assert client.get("/api/imports/1/errors.csv").status_code == 403
    assert db.scalar(select(func.count()).select_from(SalesRecord)) == 0


def test_import_needs_a_session(client):
    assert upload(client, HEADER).status_code == 401


def test_any_role_can_read_a_products_sales(client, planner, product):
    upload(client, HEADER + "2025-02-01,P001,2,\n2025-01-01,P001,1,\n")
    sales = client.get(f"/api/products/{product.id}/sales").json()
    assert [(s["period"], s["quantity"]) for s in sales] == [
        ("2025-01-01", 1), ("2025-02-01", 2)]


def test_sales_of_unknown_product_returns_404(client, planner):
    assert client.get("/api/products/999/sales").status_code == 404


def test_reading_sales_needs_a_session(client):
    assert client.get("/api/products/1/sales").status_code == 401
