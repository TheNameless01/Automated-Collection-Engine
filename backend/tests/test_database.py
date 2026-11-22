"""Database creation, migrations, transactions, CRUD, integrity, backup and restore tests."""

from __future__ import annotations

import sqlite3
import pytest

from app.database.connection import DatabaseManager
from app.collectors.base import CollectedRawRecord
from app.services.ingestion_service import ingest_raw_record


def test_migrations_seed_all_69_wilayas_and_1541_communes(temp_db: DatabaseManager) -> None:
    with temp_db.read_connection() as conn:
        wilayas = conn.execute("SELECT COUNT(*) FROM wilayas;").fetchone()[0]
        communes = conn.execute("SELECT COUNT(*) FROM communes;").fetchone()[0]
        sources = conn.execute("SELECT COUNT(*) FROM sources;").fetchone()[0]
        w59 = conn.execute("SELECT code_str, name_fr, name_ar FROM wilayas WHERE code = 59;").fetchone()
        w69 = conn.execute("SELECT code_str, name_fr, name_ar FROM wilayas WHERE code = 69;").fetchone()

    assert wilayas == 69
    assert communes == 1541
    assert sources >= 5
    assert w59["name_fr"] == "Aflou"
    assert w69["name_fr"] == "El Abiodh Sidi Cheikh"
    assert temp_db.integrity_check()["ok"] is True


def test_transaction_rollback_prevents_partial_writes(temp_db: DatabaseManager) -> None:
    with pytest.raises(RuntimeError):
        with temp_db.transaction() as conn:
            conn.execute(
                "INSERT INTO app_settings (key, value_json, updated_at) VALUES ('tx_test', '\"v\"', '2026-01-01');"
            )
            raise RuntimeError("Simulated crash mid-transaction")

    with temp_db.read_connection() as conn:
        row = conn.execute("SELECT * FROM app_settings WHERE key = 'tx_test';").fetchone()
    assert row is None


def test_crud_and_backup_restore_cycle(temp_db: DatabaseManager, geo_service) -> None:
    rec = CollectedRawRecord(
        source_key="manual_import",
        external_id="test:1",
        raw_name="Agence Synthétique Test",
        raw_phones=["0550123456"],
        raw_wilaya="Alger",
        raw_commune="Hydra",
    )
    with temp_db.transaction() as conn:
        out = ingest_raw_record(conn, rec, geo=geo_service)
        assert out.business_id is not None

    backup_path = temp_db.create_backup(reason="unit_test")
    assert backup_path is not None and backup_path.exists()

    # Mutate DB after backup
    with temp_db.transaction() as conn:
        conn.execute("UPDATE businesses SET primary_name = 'Modified After Backup' WHERE id = ?;", (out.business_id,))

    # Restore backup
    temp_db.restore_backup(backup_path.name)
    with temp_db.read_connection() as conn:
        restored = conn.execute("SELECT primary_name FROM businesses WHERE id = ?;", (out.business_id,)).fetchone()
    assert restored["primary_name"] == "Agence Synthétique Test"
