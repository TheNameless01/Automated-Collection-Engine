"""API endpoint, manual import, review operations, and HTML parser tests."""

from __future__ import annotations

import html as html_lib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.collectors.osm_overpass import parse_osm_element_tags
from app.collectors.pagesjaunes_dz import parse_pagesjaunes_listing_html
from app.collectors.pagesmaghreb import parse_pagesmaghreb_html
from app.core.config import settings
from app.database.connection import DatabaseManager
from app.main import app


def test_osm_and_pagesmaghreb_parsers() -> None:
    osm_rec = parse_osm_element_tags(
        "node",
        424242,
        36.75,
        3.05,
        {"amenity": "car_rental", "name": "Alger Auto", "phone": "0550123456"},
        source_key="osm_overpass",
        attribution="© OpenStreetMap contributors (ODbL)",
    )
    assert osm_rec is not None
    assert osm_rec.external_id == "osm:node/424242"

    # Non-car_rental tag caught via Arabic keyword
    osm_kw = parse_osm_element_tags(
        "node",
        424243,
        36.75,
        3.05,
        {"office": "company", "name": "وكالة كراء السيارات النجاح"},
        source_key="osm_overpass",
        attribution="© OpenStreetMap contributors (ODbL)",
    )
    assert osm_kw is not None

    sample_firm = json.dumps(
        {
            "id": 777,
            "corporate_name": "TEST AUTO LOCATION",
            "usual_corporate_name": "TEST AUTO Café",
            "description": "Location véhicules Alger",
            "addresses": [{"name": "10 Rue Liberté", "city": {"name": "Alger", "region": {"name": "Alger", "code": "16"}}}],
            "contacts": [
                {
                    "publish": True,
                    "contactmethods": [{"method_type": "Téléphone principal", "value": "+213.550112233"}],
                }
            ],
        },
        ensure_ascii=False,
    )
    escaped_firm = sample_firm.replace('"', r"\u0022")
    html_snippet = (
        f'<firm-card :firm="JSON.parse(\'{html_lib.escape(escaped_firm, quote=False)}\')" '
        'link="https://www.pagesmaghreb.com/entreprise/test"></firm-card>'
    )
    recs, _ = parse_pagesmaghreb_html(html_snippet, "https://www.pagesmaghreb.com/test")
    assert len(recs) == 1
    assert recs[0].raw_name == "TEST AUTO Café"
    assert recs[0].raw_phones == ["+213.550112233"]
    assert recs[0].raw_address == "10 Rue Liberté"


def test_fastapi_endpoints_crud_review_and_export(tmp_path: Path, monkeypatch) -> None:
    test_db = DatabaseManager(db_path=tmp_path / "api_test.db", backups_dir=tmp_path / "backups")
    monkeypatch.setattr("app.database.connection.db_manager", test_db)
    monkeypatch.setattr("app.api.routes.db_manager", test_db)
    monkeypatch.setattr("app.main.db_manager", test_db)
    monkeypatch.setattr(settings, "exports_dir", tmp_path / "exports")
    (tmp_path / "exports").mkdir(parents=True, exist_ok=True)

    with TestClient(app) as client:
        h = client.get("/api/health")
        assert h.status_code == 200
        assert h.json()["wilayas_count"] == 69

        # Create business manually
        c_res = client.post(
            "/api/businesses",
            json={
                "primary_name": "Test Api Agency",
                "primary_phone": "0550987654",
                "wilaya_code": 16,
                "full_address": "12 Rue Didouche Mourad",
            },
        )
        assert c_res.status_code == 200
        biz_id = c_res.json()["business_id"]

        # Edit via manual review endpoint
        u_res = client.patch(
            f"/api/businesses/{biz_id}",
            json={"verification_status": "VERIFIED", "review_notes": "Confirmed manually"},
        )
        assert u_res.status_code == 200

        # Inspect business detail & audit log
        d_res = client.get(f"/api/businesses/{biz_id}")
        assert d_res.status_code == 200
        assert d_res.json()["business"]["verification_status"] == "VERIFIED"
        assert len(d_res.json()["audit_logs"]) >= 1

        # CSV Upload import
        csv_bytes = "name,phone,wilaya,address\nImported Rent Car,0770123456,Oran,Centre Ville\n".encode("utf-8")
        up_res = client.post("/api/imports/upload", files={"file": ("test.csv", csv_bytes, "text/csv")})
        assert up_res.status_code == 200
        assert up_res.json()["total_rows"] == 1

        # Export Excel
        exp_res = client.post("/api/exports", json={"format": "xlsx", "scope": "all"})
        assert exp_res.status_code == 200
        dl_url = exp_res.json()["download_url"]
        dl_res = client.get(dl_url)
        assert dl_res.status_code == 200
        assert len(dl_res.content) > 1000
