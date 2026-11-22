"""Versioned SQLite database schema migrations and authoritative reference seeding."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.database.connection import DatabaseManager


def _migration_001_initial_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS wilayas (
            code INTEGER PRIMARY KEY,
            code_str TEXT NOT NULL UNIQUE,
            name_fr TEXT NOT NULL,
            name_ar TEXT NOT NULL,
            name_en TEXT NOT NULL,
            alt_names_json TEXT NOT NULL DEFAULT '[]',
            parent_wilaya_code INTEGER REFERENCES wilayas(code),
            center_lat REAL NOT NULL,
            center_lon REAL NOT NULL,
            min_lat REAL NOT NULL,
            max_lat REAL NOT NULL,
            min_lon REAL NOT NULL,
            max_lon REAL NOT NULL,
            boundary_geojson TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS communes (
            id INTEGER PRIMARY KEY,
            code_commune TEXT NOT NULL,
            wilaya_code INTEGER NOT NULL REFERENCES wilayas(code) ON DELETE CASCADE,
            name_fr TEXT NOT NULL,
            name_ar TEXT NOT NULL,
            daira_name_fr TEXT NOT NULL DEFAULT '',
            daira_name_ar TEXT NOT NULL DEFAULT '',
            postal_code TEXT NOT NULL DEFAULT '',
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            alt_names_json TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            base_url TEXT NOT NULL DEFAULT '',
            license_info TEXT NOT NULL DEFAULT '',
            attribution TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            rate_limit_seconds REAL NOT NULL DEFAULT 1.5,
            max_retries INTEGER NOT NULL DEFAULT 3,
            config_json TEXT NOT NULL DEFAULT '{}',
            last_run_at TEXT,
            last_status TEXT NOT NULL DEFAULT 'never_run',
            last_error TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS collection_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at TEXT NOT NULL,
            finished_at TEXT,
            stop_requested INTEGER NOT NULL DEFAULT 0,
            search_depth TEXT NOT NULL DEFAULT 'standard',
            selected_wilayas_json TEXT NOT NULL DEFAULT '[]',
            selected_communes_json TEXT NOT NULL DEFAULT '[]',
            selected_sources_json TEXT NOT NULL DEFAULT '[]',
            total_tasks INTEGER NOT NULL DEFAULT 0,
            completed_tasks INTEGER NOT NULL DEFAULT 0,
            discovered_count INTEGER NOT NULL DEFAULT 0,
            processed_count INTEGER NOT NULL DEFAULT 0,
            new_businesses_count INTEGER NOT NULL DEFAULT 0,
            merged_count INTEGER NOT NULL DEFAULT 0,
            rejected_count INTEGER NOT NULL DEFAULT 0,
            review_required_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            checkpoint_json TEXT NOT NULL DEFAULT '{}',
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS collection_wilaya_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES collection_runs(id) ON DELETE CASCADE,
            wilaya_code INTEGER NOT NULL REFERENCES wilayas(code),
            source_key TEXT NOT NULL,
            coverage_status TEXT NOT NULL DEFAULT 'not_started',
            discovered_count INTEGER NOT NULL DEFAULT 0,
            processed_count INTEGER NOT NULL DEFAULT 0,
            rejected_count INTEGER NOT NULL DEFAULT 0,
            review_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(run_id, wilaya_code, source_key)
        );

        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primary_name TEXT NOT NULL,
            name_ar TEXT NOT NULL DEFAULT '',
            name_fr TEXT NOT NULL DEFAULT '',
            name_en TEXT NOT NULL DEFAULT '',
            normalized_name TEXT NOT NULL DEFAULT '',
            primary_phone TEXT NOT NULL DEFAULT '',
            primary_phone_raw TEXT NOT NULL DEFAULT '',
            primary_phone_status TEXT NOT NULL DEFAULT 'unknown',
            full_address TEXT NOT NULL DEFAULT '',
            commune_id INTEGER REFERENCES communes(id),
            commune_name TEXT NOT NULL DEFAULT '',
            wilaya_code INTEGER REFERENCES wilayas(code),
            wilaya_name TEXT NOT NULL DEFAULT '',
            lat REAL,
            lon REAL,
            geo_assignment_method TEXT NOT NULL DEFAULT 'unknown',
            geo_uncertain INTEGER NOT NULL DEFAULT 0,
            website TEXT NOT NULL DEFAULT '',
            facebook_url TEXT NOT NULL DEFAULT '',
            instagram_url TEXT NOT NULL DEFAULT '',
            other_socials_json TEXT NOT NULL DEFAULT '[]',
            google_maps_url TEXT NOT NULL DEFAULT '',
            verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
            confidence_score REAL NOT NULL DEFAULT 0.0,
            verification_notes TEXT NOT NULL DEFAULT '',
            last_verified_at TEXT,
            first_collected_at TEXT NOT NULL,
            last_collected_at TEXT NOT NULL,
            is_merged INTEGER NOT NULL DEFAULT 0,
            merged_into_id INTEGER REFERENCES businesses(id),
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS business_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            language TEXT NOT NULL,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL DEFAULT '',
            source_id INTEGER REFERENCES sources(id),
            is_primary INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS phone_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            original_number TEXT NOT NULL,
            normalized_e164 TEXT NOT NULL DEFAULT '',
            national_format TEXT NOT NULL DEFAULT '',
            validation_status TEXT NOT NULL DEFAULT 'unknown',
            number_type TEXT NOT NULL DEFAULT 'unknown',
            carrier_hint TEXT NOT NULL DEFAULT '',
            source_id INTEGER REFERENCES sources(id),
            source_record_id INTEGER,
            is_primary INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            raw_address TEXT NOT NULL,
            normalized_address TEXT NOT NULL DEFAULT '',
            commune_id INTEGER REFERENCES communes(id),
            wilaya_code INTEGER REFERENCES wilayas(code),
            postal_code TEXT NOT NULL DEFAULT '',
            source_id INTEGER REFERENCES sources(id),
            is_primary INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS geographic_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            in_algeria INTEGER NOT NULL DEFAULT 1,
            assigned_wilaya_code INTEGER REFERENCES wilayas(code),
            assigned_commune_id INTEGER REFERENCES communes(id),
            assignment_method TEXT NOT NULL DEFAULT '',
            distance_to_commune_km REAL,
            uncertain INTEGER NOT NULL DEFAULT 0,
            source_id INTEGER REFERENCES sources(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS source_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL REFERENCES sources(id),
            collection_run_id INTEGER REFERENCES collection_runs(id),
            external_id TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            raw_name TEXT NOT NULL DEFAULT '',
            raw_name_ar TEXT NOT NULL DEFAULT '',
            raw_name_fr TEXT NOT NULL DEFAULT '',
            raw_name_en TEXT NOT NULL DEFAULT '',
            raw_phones_json TEXT NOT NULL DEFAULT '[]',
            raw_address TEXT NOT NULL DEFAULT '',
            raw_commune TEXT NOT NULL DEFAULT '',
            raw_wilaya TEXT NOT NULL DEFAULT '',
            raw_lat REAL,
            raw_lon REAL,
            raw_website TEXT NOT NULL DEFAULT '',
            raw_socials_json TEXT NOT NULL DEFAULT '{}',
            raw_google_maps_url TEXT NOT NULL DEFAULT '',
            raw_payload_json TEXT NOT NULL DEFAULT '{}',
            attribution_text TEXT NOT NULL DEFAULT '',
            collected_at TEXT NOT NULL,
            processed INTEGER NOT NULL DEFAULT 0,
            rejected INTEGER NOT NULL DEFAULT 0,
            rejection_reason TEXT NOT NULL DEFAULT '',
            business_id INTEGER REFERENCES businesses(id)
        );

        CREATE TABLE IF NOT EXISTS business_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            source_id INTEGER NOT NULL REFERENCES sources(id),
            source_record_id INTEGER NOT NULL REFERENCES source_records(id) ON DELETE CASCADE,
            source_url TEXT NOT NULL DEFAULT '',
            collected_at TEXT NOT NULL,
            UNIQUE(business_id, source_record_id)
        );

        CREATE TABLE IF NOT EXISTS verification_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            previous_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            verification_method TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            checks_json TEXT NOT NULL DEFAULT '{}',
            supporting_sources_count INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            verified_by TEXT NOT NULL DEFAULT 'system',
            verified_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS duplicate_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_a_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            business_b_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            overall_score REAL NOT NULL,
            signals_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            resolution_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            UNIQUE(business_a_id, business_b_id)
        );

        CREATE TABLE IF NOT EXISTS merge_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_business_id INTEGER NOT NULL REFERENCES businesses(id),
            source_business_id INTEGER NOT NULL REFERENCES businesses(id),
            merge_type TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            signals_json TEXT NOT NULL DEFAULT '{}',
            source_snapshot_json TEXT NOT NULL DEFAULT '{}',
            target_before_snapshot_json TEXT NOT NULL DEFAULT '{}',
            moved_source_record_ids_json TEXT NOT NULL DEFAULT '[]',
            moved_phone_ids_json TEXT NOT NULL DEFAULT '[]',
            is_reverted INTEGER NOT NULL DEFAULT 0,
            reverted_at TEXT,
            reverted_by TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS manual_review_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            decision_type TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            before_json TEXT NOT NULL DEFAULT '{}',
            after_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            actor TEXT NOT NULL DEFAULT 'user',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            logger_name TEXT NOT NULL,
            message TEXT NOT NULL,
            context_json TEXT NOT NULL DEFAULT '{}',
            run_id INTEGER,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_communes_wilaya ON communes(wilaya_code);
        CREATE INDEX IF NOT EXISTS idx_communes_coords ON communes(lat, lon);
        CREATE INDEX IF NOT EXISTS idx_businesses_wilaya ON businesses(wilaya_code);
        CREATE INDEX IF NOT EXISTS idx_businesses_commune ON businesses(commune_id);
        CREATE INDEX IF NOT EXISTS idx_businesses_status ON businesses(verification_status);
        CREATE INDEX IF NOT EXISTS idx_businesses_merged ON businesses(is_merged);
        CREATE INDEX IF NOT EXISTS idx_businesses_phone ON businesses(primary_phone);
        CREATE INDEX IF NOT EXISTS idx_businesses_norm_name ON businesses(normalized_name);
        CREATE INDEX IF NOT EXISTS idx_businesses_coords ON businesses(lat, lon);
        CREATE INDEX IF NOT EXISTS idx_phone_numbers_e164 ON phone_numbers(normalized_e164);
        CREATE INDEX IF NOT EXISTS idx_phone_numbers_biz ON phone_numbers(business_id);
        CREATE INDEX IF NOT EXISTS idx_source_records_ext ON source_records(source_id, external_id);
        CREATE INDEX IF NOT EXISTS idx_source_records_biz ON source_records(business_id);
        CREATE INDEX IF NOT EXISTS idx_source_records_run ON source_records(collection_run_id);
        CREATE INDEX IF NOT EXISTS idx_dup_candidates_status ON duplicate_candidates(status);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_app_logs_level_time ON app_logs(level, created_at);
        """
    )


MIGRATIONS: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "Initial normalized schema for DZ Car Rental Finder", _migration_001_initial_schema),
]


DEFAULT_SOURCES = [
    {
        "key": "osm_overpass",
        "name": "OpenStreetMap (Overpass API)",
        "source_type": "open_data_api",
        "base_url": "https://overpass-api.de/api/interpreter",
        "license_info": "ODbL (Open Database License) — © OpenStreetMap contributors",
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "enabled": 1,
        "rate_limit_seconds": 2.0,
        "max_retries": 3,
        "config": {
            "timeout_seconds": 60,
            "query_mode": "car_rental_and_keywords",
        },
    },
    {
        "key": "osm_pbf",
        "name": "OpenStreetMap Algeria Extract (Geofabrik PBF)",
        "source_type": "local_pbf",
        "base_url": "https://download.geofabrik.de/africa/algeria-latest.osm.pbf",
        "license_info": "ODbL (Open Database License) — © OpenStreetMap contributors / Geofabrik",
        "attribution": "© OpenStreetMap contributors (ODbL) via Geofabrik",
        "enabled": 1,
        "rate_limit_seconds": 0.5,
        "max_retries": 3,
        "config": {
            "local_pbf_filename": "algeria-latest.osm.pbf",
            "auto_download": False,
        },
    },
    {
        "key": "pagesmaghreb",
        "name": "PagesMaghreb Algeria Directory",
        "source_type": "public_directory",
        "base_url": "https://www.pagesmaghreb.com",
        "license_info": "Public business directory; robots.txt permits crawling (Allow: /)",
        "attribution": "PagesMaghreb Public Directory",
        "enabled": 1,
        "rate_limit_seconds": 2.0,
        "max_retries": 3,
        "config": {
            "max_pages_per_category": 15,
            "respect_robots_txt": True,
        },
    },
    {
        "key": "pagesjaunes_dz",
        "name": "PagesJaunes Algérie Directory",
        "source_type": "public_directory",
        "base_url": "https://www.pagesjaunes-dz.com",
        "license_info": "Public business directory; respects robots.txt disallows",
        "attribution": "PagesJaunes Algérie",
        "enabled": 1,
        "rate_limit_seconds": 2.5,
        "max_retries": 3,
        "config": {
            "max_pages": 10,
            "respect_robots_txt": True,
        },
    },
    {
        "key": "business_website",
        "name": "Public Agency Websites (Enrichment)",
        "source_type": "public_website",
        "base_url": "",
        "license_info": "Public business websites; checks robots.txt before fetching",
        "attribution": "Agency Official Website",
        "enabled": 1,
        "rate_limit_seconds": 2.0,
        "max_retries": 2,
        "config": {
            "respect_robots_txt": True,
            "max_sites_per_run": 50,
        },
    },
    {
        "key": "manual_import",
        "name": "Manual CSV / Excel / GeoJSON Import",
        "source_type": "manual_import",
        "base_url": "",
        "license_info": "User-supplied local datasets & manual Google Maps verification notes",
        "attribution": "Manual Import",
        "enabled": 1,
        "rate_limit_seconds": 0.0,
        "max_retries": 0,
        "config": {},
    },
]

DEFAULT_SETTINGS = {
    "language": "fr",
    "auto_merge_threshold": 0.88,
    "review_threshold": 0.58,
    "max_branch_distance_km": 1.5,
    "check_website_reachability": False,
    "osm_pbf_url": "https://download.geofabrik.de/africa/algeria-latest.osm.pbf",
}


def run_migrations(db: DatabaseManager, boundaries_dir: Path | None = None) -> None:
    """Apply pending schema migrations and seed reference data safely."""
    b_dir = (boundaries_dir or settings.boundaries_dir).resolve()
    db_exists = db.db_path.exists()

    with db.transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )
        applied_versions = {
            row["version"] for row in conn.execute("SELECT version FROM schema_migrations;").fetchall()
        }

    pending = [m for m in MIGRATIONS if m[0] not in applied_versions]
    if pending and db_exists:
        db.create_backup(reason="pre_migration")

    for version, desc, fn in pending:
        with db.transaction() as conn:
            fn(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?);",
                (version, desc, datetime.now(timezone.utc).isoformat()),
            )

    seed_reference_data(db, b_dir)


def seed_reference_data(db: DatabaseManager, boundaries_dir: Path) -> None:
    """Seed all 69 wilayas, 1,541 communes, default sources, and settings idempotently."""
    wilayas_file = boundaries_dir / "algeria_69_wilayas.json"
    communes_file = boundaries_dir / "algeria_1541_communes.json"

    with db.transaction() as conn:
        now = datetime.now(timezone.utc).isoformat()

        existing_w = conn.execute("SELECT COUNT(*) AS cnt FROM wilayas;").fetchone()["cnt"]
        if existing_w < 69 and wilayas_file.exists():
            wilayas_data = json.loads(wilayas_file.read_text(encoding="utf-8"))
            # Insert parent wilayas first (1..48), then 49..69
            wilayas_sorted = sorted(wilayas_data, key=lambda x: x["code"])
            for w in wilayas_sorted:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO wilayas (
                        code, code_str, name_fr, name_ar, name_en, alt_names_json,
                        parent_wilaya_code, center_lat, center_lon,
                        min_lat, max_lat, min_lon, max_lon, boundary_geojson, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                    """,
                    (
                        w["code"],
                        w["code_str"],
                        w["name_fr"],
                        w["name_ar"],
                        w["name_en"],
                        json.dumps(w["alt_names"], ensure_ascii=False),
                        w.get("parent_wilaya_code"),
                        w["center_lat"],
                        w["center_lon"],
                        w["min_lat"],
                        w["max_lat"],
                        w["min_lon"],
                        w["max_lon"],
                        json.dumps(w["boundary_geojson"]),
                    ),
                )

        existing_c = conn.execute("SELECT COUNT(*) AS cnt FROM communes;").fetchone()["cnt"]
        if existing_c < 1541 and communes_file.exists():
            communes_data = json.loads(communes_file.read_text(encoding="utf-8"))
            for c in communes_data:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO communes (
                        id, code_commune, wilaya_code, name_fr, name_ar,
                        daira_name_fr, daira_name_ar, postal_code, lat, lon, alt_names_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        c["id"],
                        c["code_commune"],
                        c["wilaya_code"],
                        c["name_fr"],
                        c["name_ar"],
                        c.get("daira_name_fr", ""),
                        c.get("daira_name_ar", ""),
                        c.get("code_commune", ""),
                        c["lat"],
                        c["lon"],
                        json.dumps([c["name_fr"], c["name_ar"]], ensure_ascii=False),
                    ),
                )

        for src in DEFAULT_SOURCES:
            conn.execute(
                """
                INSERT OR IGNORE INTO sources (
                    key, name, source_type, base_url, license_info, attribution,
                    enabled, rate_limit_seconds, max_retries, config_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    src["key"],
                    src["name"],
                    src["source_type"],
                    src["base_url"],
                    src["license_info"],
                    src["attribution"],
                    src["enabled"],
                    src["rate_limit_seconds"],
                    src["max_retries"],
                    json.dumps(src["config"], ensure_ascii=False),
                ),
            )

        for key, val in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?);",
                (key, json.dumps(val, ensure_ascii=False), now),
            )
