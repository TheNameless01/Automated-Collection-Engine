"""Tests for Algerian phone normalization and deduplication engine rules."""

from __future__ import annotations

from app.collectors.base import CollectedRawRecord
from app.database.connection import DatabaseManager
from app.deduplication.engine import evaluate_duplicate_pair, revert_merge
from app.processors.phone_processor import normalize_algerian_phone
from app.services.ingestion_service import ingest_raw_record


def test_algerian_phone_formats() -> None:
    p1 = normalize_algerian_phone("+213 550 12 34 56")
    assert p1.normalized_e164 == "+213550123456"
    assert p1.validation_status == "valid_format"
    assert p1.number_type == "mobile"

    p2 = normalize_algerian_phone("00213-661-98-76-54")
    assert p2.normalized_e164 == "+213661987654"
    assert p2.validation_status == "valid_format"

    p3 = normalize_algerian_phone("021 63 45 78")
    assert p3.normalized_e164 == "+21321634578"
    assert p3.validation_status == "valid_format"
    assert p3.number_type == "fixed_line"

    p4 = normalize_algerian_phone("+213.0555014340")
    assert p4.normalized_e164 == "+213555014340"
    assert p4.validation_status == "valid_format"

    bad = normalize_algerian_phone("12345")
    assert bad.validation_status == "invalid_format"


def test_dedup_auto_merges_and_reverts_arabic_french_variants(temp_db: DatabaseManager, geo_service) -> None:
    r1 = CollectedRawRecord(
        source_key="osm_overpass",
        external_id="osm:node/1001",
        source_url="https://www.openstreetmap.org/node/1001",
        raw_name="Agence El Amal Location Voitures",
        raw_phones=["0550112233"],
        raw_address="12 Rue Didouche Mourad, Alger Centre",
        raw_wilaya="Alger",
        raw_lat=36.768,
        raw_lon=3.051,
    )
    r2 = CollectedRawRecord(
        source_key="pagesmaghreb",
        external_id="pagesmaghreb:9999",
        source_url="https://www.pagesmaghreb.com/example",
        raw_name="وكالة الامل لكراء السيارات",
        raw_name_ar="وكالة الامل لكراء السيارات",
        raw_phones=["+213 550 11 22 33"],
        raw_address="12 Rue Didouche Mourad, Alger",
        raw_wilaya="Alger",
        raw_lat=36.7681,
        raw_lon=3.0511,
        raw_website="https://elamal-auto.dz",
    )

    with temp_db.transaction() as conn:
        o1 = ingest_raw_record(conn, r1, geo=geo_service)
        o2 = ingest_raw_record(conn, r2, geo=geo_service)
        assert o1.action == "new"
        assert o2.action == "auto_merged"
        assert o2.business_id == o1.business_id

        active_cnt = conn.execute("SELECT COUNT(*) FROM businesses WHERE is_merged = 0;").fetchone()[0]
        assert active_cnt == 1

        mh = conn.execute("SELECT id FROM merge_history WHERE is_reverted = 0;").fetchone()
        assert mh is not None
        revert_merge(conn, int(mh["id"]), actor="test")

        restored_cnt = conn.execute("SELECT COUNT(*) FROM businesses WHERE is_merged = 0;").fetchone()[0]
        assert restored_cnt == 2


def test_shared_phone_alone_and_branches_never_auto_merge() -> None:
    # Different companies sharing a call-center phone without corroborating address/name
    a = {"primary_name": "Alpha Rent Car", "full_address": "Rue A", "wilaya_code": 16, "commune_id": 1, "lat": None, "lon": None, "website": "", "facebook_url": "", "instagram_url": ""}
    b = {"primary_name": "Zeta Mobility", "full_address": "Boulevard B", "wilaya_code": 16, "commune_id": 1, "lat": None, "lon": None, "website": "", "facebook_url": "", "instagram_url": ""}
    ev_phone_only = evaluate_duplicate_pair(a, b, phones_a={"+213550000111"}, phones_b={"+213550000111"}, ext_ids_a=set(), ext_ids_b=set())
    assert ev_phone_only.decision != "auto_merge"

    # Two branches of the same company in different communes/distance
    br1 = {"primary_name": "Rapide Auto - Annexe Dar El Beida", "full_address": "Aeroport Dar El Beida", "wilaya_code": 16, "commune_id": 10, "lat": 36.691, "lon": 3.215, "website": "https://rapide.dz", "facebook_url": "", "instagram_url": ""}
    br2 = {"primary_name": "Rapide Auto - Annexe Hydra", "full_address": "Rue Hydra", "wilaya_code": 16, "commune_id": 20, "lat": 36.743, "lon": 3.045, "website": "https://rapide.dz", "facebook_url": "", "instagram_url": ""}
    ev_branch = evaluate_duplicate_pair(br1, br2, phones_a={"+213550998877"}, phones_b={"+213550998877"}, ext_ids_a=set(), ext_ids_b=set())
    assert ev_branch.decision != "auto_merge"
