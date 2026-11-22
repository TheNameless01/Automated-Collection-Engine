"""Ingestion pipeline: raw source record -> normalization -> geo assignment -> deduplication -> verification."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.collectors.base import CollectedRawRecord
from app.deduplication.engine import evaluate_duplicate_pair, merge_businesses
from app.geography.service import GeographyService, get_geography_service
from app.processors.phone_processor import normalize_algerian_phone, split_raw_phone_strings
from app.processors.text_normalizer import normalize_business_name, normalize_url
from app.verification.engine import verify_and_persist


@dataclass
class IngestionOutcome:
    source_record_id: int
    business_id: int | None
    action: str  # new | auto_merged | review_candidate | updated_source | rejected
    rejected_reason: str = ""
    needs_review: bool = False


def _load_thresholds(conn: sqlite3.Connection) -> tuple[float, float, float]:
    def _get(key: str, default: float) -> float:
        r = conn.execute("SELECT value_json FROM app_settings WHERE key = ?;", (key,)).fetchone()
        return float(json.loads(r["value_json"])) if r else default

    return (
        _get("auto_merge_threshold", 0.88),
        _get("review_threshold", 0.58),
        _get("max_branch_distance_km", 1.5),
    )


def _find_candidate_businesses(
    conn: sqlite3.Connection,
    *,
    external_id: str,
    source_id: int,
    phones_e164: list[str],
    wilaya_code: int | None,
    website_domain: str,
) -> list[dict[str, Any]]:
    """Query indexed candidate businesses efficiently without loading the entire DB."""
    candidate_ids: set[int] = set()

    # 1. Exact source + external_id match
    if external_id:
        for r in conn.execute(
            "SELECT business_id FROM source_records WHERE source_id = ? AND external_id = ? AND business_id IS NOT NULL;",
            (source_id, external_id),
        ).fetchall():
            candidate_ids.add(int(r["business_id"]))

    # 2. Phone match
    if phones_e164:
        ph = ",".join("?" for _ in phones_e164)
        for r in conn.execute(
            f"SELECT DISTINCT business_id FROM phone_numbers WHERE normalized_e164 IN ({ph});",
            phones_e164,
        ).fetchall():
            candidate_ids.add(int(r["business_id"]))

    # 3. Same wilaya active businesses (bounded)
    if wilaya_code is not None:
        for r in conn.execute(
            "SELECT id FROM businesses WHERE is_merged = 0 AND wilaya_code = ? ORDER BY id DESC LIMIT 250;",
            (wilaya_code,),
        ).fetchall():
            candidate_ids.add(int(r["id"]))

    # 4. Same website domain
    if website_domain:
        for r in conn.execute(
            "SELECT id FROM businesses WHERE is_merged = 0 AND website LIKE ? LIMIT 25;",
            (f"%{website_domain}%",),
        ).fetchall():
            candidate_ids.add(int(r["id"]))

    if not candidate_ids:
        return []

    placeholders = ",".join("?" for _ in candidate_ids)
    rows = conn.execute(
        f"SELECT * FROM businesses WHERE id IN ({placeholders}) AND is_merged = 0;",
        list(candidate_ids),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_business_signals(conn: sqlite3.Connection, business_id: int) -> tuple[set[str], set[str]]:
    phones = {
        r["normalized_e164"]
        for r in conn.execute(
            "SELECT normalized_e164 FROM phone_numbers WHERE business_id = ? AND normalized_e164 != '';",
            (business_id,),
        ).fetchall()
    }
    ext_ids = {
        r["external_id"]
        for r in conn.execute(
            "SELECT external_id FROM source_records WHERE business_id = ? AND external_id != '';",
            (business_id,),
        ).fetchall()
    }
    return phones, ext_ids


def ingest_raw_record(
    conn: sqlite3.Connection,
    rec: CollectedRawRecord,
    *,
    run_id: int | None = None,
    geo: GeographyService | None = None,
) -> IngestionOutcome:
    """Persist raw evidence and process into normalized, deduplicated, verified business records."""
    geo_svc = geo or get_geography_service()
    now = datetime.now(timezone.utc).isoformat()

    src_row = conn.execute("SELECT id FROM sources WHERE key = ?;", (rec.source_key,)).fetchone()
    if not src_row:
        raise ValueError(f"Unknown source key: {rec.source_key}")
    source_id = int(src_row["id"])

    # Insert raw source_record immediately to preserve complete provenance
    cur_sr = conn.execute(
        """
        INSERT INTO source_records (
            source_id, collection_run_id, external_id, source_url,
            raw_name, raw_name_ar, raw_name_fr, raw_name_en,
            raw_phones_json, raw_address, raw_commune, raw_wilaya,
            raw_lat, raw_lon, raw_website, raw_socials_json,
            raw_google_maps_url, raw_payload_json, attribution_text,
            collected_at, processed, rejected
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0);
        """,
        (
            source_id,
            run_id,
            rec.external_id,
            rec.source_url,
            rec.raw_name,
            rec.raw_name_ar,
            rec.raw_name_fr,
            rec.raw_name_en,
            json.dumps(rec.raw_phones, ensure_ascii=False),
            rec.raw_address,
            rec.raw_commune,
            rec.raw_wilaya,
            rec.raw_lat,
            rec.raw_lon,
            rec.raw_website,
            json.dumps(
                {
                    "facebook": rec.raw_facebook,
                    "instagram": rec.raw_instagram,
                    "other": rec.raw_other_socials,
                },
                ensure_ascii=False,
            ),
            rec.raw_google_maps_url,
            json.dumps(rec.raw_payload, ensure_ascii=False),
            rec.attribution_text,
            now,
        ),
    )
    sr_id = int(cur_sr.lastrowid)

    # Reject empty / unusable records transparently
    primary_name = (rec.raw_name or rec.raw_name_fr or rec.raw_name_ar or rec.raw_name_en).strip()
    if not primary_name:
        conn.execute(
            "UPDATE source_records SET processed = 1, rejected = 1, rejection_reason = ? WHERE id = ?;",
            ("Missing business name", sr_id),
        )
        return IngestionOutcome(sr_id, None, "rejected", "Missing business name")

    # Normalize phones
    raw_phone_tokens = split_raw_phone_strings(rec.raw_phones)
    parsed_phones = [normalize_algerian_phone(p) for p in raw_phone_tokens]
    valid_e164s = [p.normalized_e164 for p in parsed_phones if p.normalized_e164]
    primary_parsed = next((p for p in parsed_phones if p.validation_status == "valid_format"), None) or (
        parsed_phones[0] if parsed_phones else None
    )

    # Geographic assignment
    geo_res = geo_svc.assign(
        lat=rec.raw_lat,
        lon=rec.raw_lon,
        raw_wilaya=rec.raw_wilaya,
        raw_commune=rec.raw_commune,
        raw_address=rec.raw_address,
    )

    # Reject coordinates definitively outside Algeria with no Algerian wilaya text
    if rec.raw_lat is not None and rec.raw_lon is not None and not geo_res.in_algeria and geo_res.wilaya_code is None:
        reason = geo_res.notes or "Coordinates outside Algeria"
        conn.execute(
            "UPDATE source_records SET processed = 1, rejected = 1, rejection_reason = ? WHERE id = ?;",
            (reason, sr_id),
        )
        return IngestionOutcome(sr_id, None, "rejected", reason)

    website = normalize_url(rec.raw_website)
    facebook = normalize_url(rec.raw_facebook)
    instagram = normalize_url(rec.raw_instagram)
    other_socials = [u for u in (normalize_url(s) for s in rec.raw_other_socials) if u]
    gmaps_url = normalize_url(rec.raw_google_maps_url)

    # Detect Arabic/French/English names without inventing missing translations
    name_ar = rec.raw_name_ar.strip()
    name_fr = rec.raw_name_fr.strip()
    name_en = rec.raw_name_en.strip()
    if not name_ar and any("\u0600" <= ch <= "\u06FF" for ch in primary_name):
        name_ar = primary_name
    elif not name_fr and any("a" <= ch.lower() <= "z" for ch in primary_name):
        name_fr = primary_name

    # Check if this exact (source_id, external_id) is already linked to an active business
    existing_link = None
    if rec.external_id:
        existing_link = conn.execute(
            """
            SELECT b.* FROM source_records sr
            JOIN businesses b ON b.id = sr.business_id
            WHERE sr.source_id = ? AND sr.external_id = ? AND sr.business_id IS NOT NULL AND b.is_merged = 0
            LIMIT 1;
            """,
            (source_id, rec.external_id),
        ).fetchone()

    if existing_link:
        biz_id = int(existing_link["id"])
        conn.execute(
            "UPDATE source_records SET business_id = ?, processed = 1 WHERE id = ?;",
            (biz_id, sr_id),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO business_sources (business_id, source_id, source_record_id, source_url, collected_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            (biz_id, source_id, sr_id, rec.source_url, now),
        )
        conn.execute("UPDATE businesses SET last_collected_at = ?, updated_at = ? WHERE id = ?;", (now, now, biz_id))
        ev = verify_and_persist(conn, biz_id, geo=geo_svc)
        return IngestionOutcome(sr_id, biz_id, "updated_source", needs_review=(ev.status == "NEEDS_REVIEW"))

    # Create normalized business record first, then run deduplication against candidates
    norm_name = normalize_business_name(primary_name)
    cur_biz = conn.execute(
        """
        INSERT INTO businesses (
            primary_name, name_ar, name_fr, name_en, normalized_name,
            primary_phone, primary_phone_raw, primary_phone_status,
            full_address, commune_id, commune_name, wilaya_code, wilaya_name,
            lat, lon, geo_assignment_method, geo_uncertain,
            website, facebook_url, instagram_url, other_socials_json, google_maps_url,
            verification_status, confidence_score, verification_notes,
            first_collected_at, last_collected_at, is_merged, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNVERIFIED', 0.0, '', ?, ?, 0, ?, ?, ?);
        """,
        (
            primary_name,
            name_ar,
            name_fr,
            name_en,
            norm_name,
            primary_parsed.normalized_e164 if primary_parsed and primary_parsed.normalized_e164 else "",
            primary_parsed.original_number if primary_parsed else "",
            primary_parsed.validation_status if primary_parsed else "unknown",
            rec.raw_address.strip(),
            geo_res.commune_id,
            geo_res.commune_name,
            geo_res.wilaya_code,
            geo_res.wilaya_name,
            rec.raw_lat,
            rec.raw_lon,
            geo_res.method,
            1 if geo_res.uncertain else 0,
            website,
            facebook,
            instagram,
            json.dumps(other_socials, ensure_ascii=False),
            gmaps_url,
            now,
            now,
            rec.notes,
            now,
            now,
        ),
    )
    new_biz_id = int(cur_biz.lastrowid)

    # Link source_record & business_sources
    conn.execute("UPDATE source_records SET business_id = ?, processed = 1 WHERE id = ?;", (new_biz_id, sr_id))
    conn.execute(
        """
        INSERT OR IGNORE INTO business_sources (business_id, source_id, source_record_id, source_url, collected_at)
        VALUES (?, ?, ?, ?, ?);
        """,
        (new_biz_id, source_id, sr_id, rec.source_url, now),
    )

    # Insert business_names
    for lang, val, is_p in (
        ("fr", name_fr, 1 if name_fr == primary_name else 0),
        ("ar", name_ar, 1 if name_ar == primary_name else 0),
        ("en", name_en, 1 if name_en == primary_name else 0),
    ):
        if val:
            conn.execute(
                """
                INSERT INTO business_names (business_id, language, name, normalized_name, source_id, is_primary)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (new_biz_id, lang, val, normalize_business_name(val), source_id, is_p),
            )

    # Insert phone_numbers
    for idx, pp in enumerate(parsed_phones):
        if not pp.original_number:
            continue
        conn.execute(
            """
            INSERT INTO phone_numbers (
                business_id, original_number, normalized_e164, national_format,
                validation_status, number_type, carrier_hint, source_id, source_record_id, is_primary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                new_biz_id,
                pp.original_number,
                pp.normalized_e164,
                pp.national_format,
                pp.validation_status,
                pp.number_type,
                pp.carrier_hint,
                source_id,
                sr_id,
                1 if idx == 0 else 0,
                now,
            ),
        )

    # Insert address & geographic_location
    if rec.raw_address.strip():
        conn.execute(
            """
            INSERT INTO addresses (business_id, raw_address, normalized_address, commune_id, wilaya_code, source_id, is_primary)
            VALUES (?, ?, ?, ?, ?, ?, 1);
            """,
            (new_biz_id, rec.raw_address.strip(), rec.raw_address.strip().lower(), geo_res.commune_id, geo_res.wilaya_code, source_id),
        )

    if rec.raw_lat is not None and rec.raw_lon is not None:
        conn.execute(
            """
            INSERT INTO geographic_locations (
                business_id, lat, lon, in_algeria, assigned_wilaya_code, assigned_commune_id,
                assignment_method, distance_to_commune_km, uncertain, source_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                new_biz_id,
                rec.raw_lat,
                rec.raw_lon,
                1 if geo_res.in_algeria else 0,
                geo_res.wilaya_code,
                geo_res.commune_id,
                geo_res.method,
                geo_res.distance_to_commune_km,
                1 if geo_res.uncertain else 0,
                source_id,
                now,
            ),
        )

    # Run Deduplication against existing candidates
    from app.processors.text_normalizer import extract_domain

    domain = extract_domain(website)
    candidates = _find_candidate_businesses(
        conn,
        external_id=rec.external_id,
        source_id=source_id,
        phones_e164=valid_e164s,
        wilaya_code=geo_res.wilaya_code,
        website_domain=domain,
    )
    candidates = [c for c in candidates if int(c["id"]) != new_biz_id]

    auto_thresh, rev_thresh, max_branch_km = _load_thresholds(conn)
    new_biz_dict = dict(conn.execute("SELECT * FROM businesses WHERE id = ?;", (new_biz_id,)).fetchone())
    new_phones = set(valid_e164s)
    new_ext_ids = {rec.external_id} if rec.external_id else set()

    best_merge_cand: tuple[int, float, dict[str, Any]] | None = None
    review_cands: list[tuple[int, float, dict[str, Any]]] = []

    for cand in candidates:
        cid = int(cand["id"])
        c_phones, c_ext = _get_business_signals(conn, cid)
        ev_dup = evaluate_duplicate_pair(
            cand,
            new_biz_dict,
            phones_a=c_phones,
            phones_b=new_phones,
            ext_ids_a=c_ext,
            ext_ids_b=new_ext_ids,
            auto_merge_threshold=auto_thresh,
            review_threshold=rev_thresh,
            max_branch_distance_km=max_branch_km,
        )
        if ev_dup.decision == "auto_merge":
            if best_merge_cand is None or ev_dup.score > best_merge_cand[1]:
                best_merge_cand = (cid, ev_dup.score, ev_dup.signals)
        elif ev_dup.decision == "review":
            review_cands.append((cid, ev_dup.score, ev_dup.signals))

    if best_merge_cand is not None:
        target_id, score, sigs = best_merge_cand
        merge_businesses(
            conn,
            target_id=target_id,
            source_id=new_biz_id,
            merge_type="auto",
            confidence_score=score,
            signals=sigs,
            actor="dedup_engine",
        )
        ev = verify_and_persist(conn, target_id, geo=geo_svc)
        return IngestionOutcome(sr_id, target_id, "auto_merged", needs_review=(ev.status == "NEEDS_REVIEW"))

    for cid, score, sigs in review_cands[:3]:
        a_id, b_id = min(cid, new_biz_id), max(cid, new_biz_id)
        conn.execute(
            """
            INSERT OR IGNORE INTO duplicate_candidates (
                business_a_id, business_b_id, overall_score, signals_json, status, created_at
            ) VALUES (?, ?, ?, ?, 'pending', ?);
            """,
            (a_id, b_id, score, json.dumps(sigs, ensure_ascii=False), now),
        )

    ev = verify_and_persist(conn, new_biz_id, geo=geo_svc)
    action = "review_candidate" if review_cands else "new"
    return IngestionOutcome(
        sr_id,
        new_biz_id,
        action,
        needs_review=(ev.status == "NEEDS_REVIEW" or bool(review_cands)),
    )
