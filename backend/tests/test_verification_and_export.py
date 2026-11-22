"""Tests for automatic verification rules and 69-wilaya Excel/CSV exports."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from app.collectors.base import CollectedRawRecord
from app.database.connection import DatabaseManager
from app.exporters.exporter import export_csv, export_excel
from app.services.ingestion_service import ingest_raw_record
from app.verification.engine import verify_and_persist


def test_verification_never_marks_incomplete_record_verified(temp_db: DatabaseManager, geo_service) -> None:
    incomplete = CollectedRawRecord(
        source_key="pagesmaghreb",
        external_id="pm:1",
        raw_name="Location Incomplète",
        raw_wilaya="Oran",
    )
    complete = CollectedRawRecord(
        source_key="osm_overpass",
        external_id="osm:node/200",
        raw_name="Oran Car Hire",
        raw_name_ar="وهران لكراء السيارات",
        raw_phones=["+213555443322"],
        raw_address="15 Boulevard de l'ALN, Oran",
        raw_lat=35.6971,
        raw_lon=-0.6308,
        raw_website="https://orancar.dz",
    )
    invalid_url_rec = CollectedRawRecord(
        source_key="manual_import",
        external_id="m:badurl",
        raw_name="Bad URL Agency",
        raw_phones=["0550123123"],
        raw_wilaya="Blida",
        raw_website="not a valid url",
    )
    with temp_db.transaction() as conn:
        o_inc = ingest_raw_record(conn, incomplete, geo=geo_service)
        o_comp = ingest_raw_record(conn, complete, geo=geo_service)
        o_bad = ingest_raw_record(conn, invalid_url_rec, geo=geo_service)

        ev_inc = verify_and_persist(conn, o_inc.business_id, geo=geo_service)
        ev_comp = verify_and_persist(conn, o_comp.business_id, geo=geo_service)
        ev_bad = verify_and_persist(conn, o_bad.business_id, geo=geo_service)

    assert ev_inc.status == "UNVERIFIED"
    assert ev_comp.status == "VERIFIED"
    # Invalid URL syntax normalized out or flagged if set directly
    assert ev_bad.status in ("UNVERIFIED", "NEEDS_REVIEW")


def test_excel_and_csv_exports_include_all_69_wilayas_and_arabic_utf8(
    temp_db: DatabaseManager, geo_service, tmp_path: Path
) -> None:
    rec = CollectedRawRecord(
        source_key="manual_import",
        external_id="exp:1",
        raw_name="وكالة السعادة لكراء السيارات",
        raw_name_ar="وكالة السعادة لكراء السيارات",
        raw_phones=["0661223344"],
        raw_address="حي النصر، بوسعادة",
        raw_wilaya="Bou Saâda",
        raw_lat=35.2167,
        raw_lon=4.1833,
    )
    with temp_db.transaction() as conn:
        ingest_raw_record(conn, rec, geo=geo_service)

    with temp_db.read_connection() as conn:
        xlsx_path = export_excel(conn, exports_dir=tmp_path, scope="all")
        csv_path = export_csv(conn, exports_dir=tmp_path, scope="all")

    assert xlsx_path.exists()
    wb = openpyxl.load_workbook(xlsx_path)
    # 4 summary sheets + 69 wilaya sheets = 73 sheets
    assert len(wb.sheetnames) == 73
    assert wb.sheetnames[:4] == ["MASTER", "STATISTICS", "SOURCES", "REVIEW_REQUIRED"]
    assert wb["MASTER"].max_row == 2
    assert "وكالة السعادة لكراء السيارات" in str(wb["MASTER"].cell(row=2, column=2).value)
    # Wilaya 68 (Bou Saada) sheet must have the record; Wilaya 01 (Adrar) must exist with header only
    assert wb["68-Bou Saâda"].max_row == 2
    assert wb["01-Adrar"].max_row == 1

    raw_bytes = csv_path.read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM for Excel
    csv_text = raw_bytes.decode("utf-8-sig")
    assert "وكالة السعادة لكراء السيارات" in csv_text
