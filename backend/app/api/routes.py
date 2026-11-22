"""FastAPI REST API routes for DZ Car Rental Finder."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.collectors.base import CollectedRawRecord
from app.collectors.manual_import import parse_manual_import_bytes
from app.collectors.osm_pbf import download_algeria_pbf
from app.core.config import safe_resolve_within, settings
from app.database.connection import db_manager
from app.deduplication.engine import evaluate_duplicate_pair, merge_businesses, revert_merge
from app.exporters.exporter import export_csv, export_excel
from app.geography.service import get_geography_service
from app.processors.phone_processor import normalize_algerian_phone
from app.processors.text_normalizer import normalize_business_name, normalize_url
from app.schemas.api_models import (
    BusinessCreateRequest,
    BusinessUpdateRequest,
    CollectionStartRequest,
    DuplicateResolveRequest,
    ExportCreateRequest,
    RestoreBackupRequest,
    SettingsUpdateRequest,
    SourceUpdateRequest,
)
from app.services.collection_engine import ADAPTER_REGISTRY, collection_engine
from app.services.ingestion_service import ingest_raw_record
from app.verification.engine import verify_and_persist

logger = logging.getLogger("dz_finder.api")
router = APIRouter(prefix="/api")

_pbf_download_state: dict[str, Any] = {
    "downloading": False,
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "error": "",
    "completed": False,
}


@router.get("/health")
def health() -> dict[str, Any]:
    with db_manager.read_connection() as conn:
        w_cnt = conn.execute("SELECT COUNT(*) AS c FROM wilayas;").fetchone()["c"]
        c_cnt = conn.execute("SELECT COUNT(*) AS c FROM communes;").fetchone()["c"]
        b_cnt = conn.execute("SELECT COUNT(*) AS c FROM businesses WHERE is_merged = 0;").fetchone()["c"]
    return {
        "status": "ok",
        "app": settings.app_name,
        "wilayas_count": w_cnt,
        "communes_count": c_cnt,
        "businesses_count": b_cnt,
        "active_run_id": collection_engine.get_active_run_id(),
    }


@router.get("/dashboard/summary")
def dashboard_summary() -> dict[str, Any]:
    with db_manager.read_connection() as conn:
        counts = dict(
            conn.execute(
                """
                SELECT
                    COUNT(*) AS total_businesses,
                    SUM(CASE WHEN verification_status = 'VERIFIED' THEN 1 ELSE 0 END) AS verified_count,
                    SUM(CASE WHEN verification_status = 'UNVERIFIED' THEN 1 ELSE 0 END) AS unverified_count,
                    SUM(CASE WHEN verification_status = 'NEEDS_REVIEW' OR geo_uncertain = 1 THEN 1 ELSE 0 END) AS review_count,
                    SUM(CASE WHEN verification_status = 'CLOSED' THEN 1 ELSE 0 END) AS closed_count,
                    SUM(CASE WHEN primary_phone = '' THEN 1 ELSE 0 END) AS missing_phone_count,
                    SUM(CASE WHEN full_address = '' THEN 1 ELSE 0 END) AS missing_address_count,
                    SUM(CASE WHEN lat IS NULL OR lon IS NULL THEN 1 ELSE 0 END) AS missing_coords_count,
                    SUM(CASE WHEN website = '' THEN 1 ELSE 0 END) AS missing_website_count
                FROM businesses
                WHERE is_merged = 0;
                """
            ).fetchone()
        )
        dup_pending = conn.execute(
            "SELECT COUNT(*) AS c FROM duplicate_candidates WHERE status = 'pending';"
        ).fetchone()["c"]
        runs_total = conn.execute("SELECT COUNT(*) AS c FROM collection_runs;").fetchone()["c"]
        last_run = conn.execute(
            "SELECT id, status, started_at, finished_at, discovered_count FROM collection_runs ORDER BY id DESC LIMIT 1;"
        ).fetchone()

        by_wilaya = [
            dict(r)
            for r in conn.execute(
                """
                SELECT w.code, w.code_str, w.name_fr, w.name_ar,
                       COUNT(b.id) AS total_count,
                       SUM(CASE WHEN b.verification_status = 'VERIFIED' THEN 1 ELSE 0 END) AS verified_count
                FROM wilayas w
                LEFT JOIN businesses b ON b.wilaya_code = w.code AND b.is_merged = 0
                GROUP BY w.code
                ORDER BY total_count DESC, w.code ASC;
                """
            ).fetchall()
        ]

        source_coverage = [
            dict(r)
            for r in conn.execute(
                """
                SELECT s.key, s.name, s.enabled, s.last_status, s.last_run_at,
                       COUNT(DISTINCT bs.business_id) AS business_count
                FROM sources s
                LEFT JOIN business_sources bs ON bs.source_id = s.id
                GROUP BY s.id
                ORDER BY business_count DESC, s.id ASC;
                """
            ).fetchall()
        ]

    return {
        **{k: (v or 0) for k, v in counts.items()},
        "suspected_duplicates_count": dup_pending,
        "collection_runs_count": runs_total,
        "last_collection_run": dict(last_run) if last_run else None,
        "active_run_id": collection_engine.get_active_run_id(),
        "by_wilaya": by_wilaya,
        "source_coverage": source_coverage,
    }


@router.get("/wilayas")
def list_wilayas() -> list[dict[str, Any]]:
    with db_manager.read_connection() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT w.code, w.code_str, w.name_fr, w.name_ar, w.name_en,
                       w.parent_wilaya_code, w.center_lat, w.center_lon,
                       (SELECT COUNT(*) FROM communes c WHERE c.wilaya_code = w.code) AS total_communes,
                       COUNT(b.id) AS discovered_count,
                       SUM(CASE WHEN b.verification_status = 'VERIFIED' THEN 1 ELSE 0 END) AS verified_count,
                       SUM(CASE WHEN b.verification_status = 'UNVERIFIED' THEN 1 ELSE 0 END) AS unverified_count,
                       SUM(CASE WHEN b.verification_status = 'NEEDS_REVIEW' OR b.geo_uncertain = 1 THEN 1 ELSE 0 END) AS review_count,
                       COUNT(DISTINCT CASE WHEN b.commune_id IS NOT NULL THEN b.commune_id END) AS communes_covered
                FROM wilayas w
                LEFT JOIN businesses b ON b.wilaya_code = w.code AND b.is_merged = 0
                GROUP BY w.code
                ORDER BY w.code ASC;
                """
            ).fetchall()
        ]

        # Attach latest collection status & sources used per wilaya
        src_by_w: dict[int, list[str]] = {}
        for sr in conn.execute(
            """
            SELECT DISTINCT b.wilaya_code, s.name AS source_name
            FROM businesses b
            JOIN business_sources bs ON bs.business_id = b.id
            JOIN sources s ON s.id = bs.source_id
            WHERE b.is_merged = 0 AND b.wilaya_code IS NOT NULL;
            """
        ).fetchall():
            src_by_w.setdefault(int(sr["wilaya_code"]), []).append(sr["source_name"])

        cov_by_w: dict[int, str] = {}
        for cr in conn.execute(
            """
            SELECT wilaya_code, coverage_status
            FROM collection_wilaya_progress
            WHERE run_id = (SELECT MAX(id) FROM collection_runs);
            """
        ).fetchall():
            wc = int(cr["wilaya_code"])
            st = cr["coverage_status"]
            # Prefer completed/unavailable over no_results when aggregating multiple sources
            prev = cov_by_w.get(wc)
            if prev is None or (prev in ("not_started", "no_results_found") and st == "collection_completed"):
                cov_by_w[wc] = st

    for r in rows:
        wc = int(r["code"])
        r["sources_used"] = src_by_w.get(wc, [])
        r["collection_status"] = cov_by_w.get(wc, "not_collected")
    return rows


@router.get("/wilayas/{code}/communes")
def list_wilaya_communes(code: int) -> list[dict[str, Any]]:
    with db_manager.read_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, code_commune, wilaya_code, name_fr, name_ar, daira_name_fr, daira_name_ar, lat, lon
            FROM communes
            WHERE wilaya_code = ?
            ORDER BY name_fr ASC;
            """,
            (code,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/businesses")
def list_businesses(
    search: str = "",
    wilaya_code: int | None = None,
    commune_id: int | None = None,
    verification_status: str = "",
    source_key: str = "",
    has_phone: bool | None = None,
    has_address: bool | None = None,
    has_website: bool | None = None,
    has_coords: bool | None = None,
    needs_review_only: bool = False,
    date_from: str = "",
    date_to: str = "",
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    where = ["b.is_merged = 0"]
    params: list[Any] = []

    if search.strip():
        q = f"%{search.strip()}%"
        where.append(
            "(b.primary_name LIKE ? OR b.name_ar LIKE ? OR b.name_fr LIKE ? OR b.primary_phone LIKE ? OR b.full_address LIKE ? OR b.commune_name LIKE ?)"
        )
        params.extend([q, q, q, q, q, q])
    if wilaya_code is not None:
        where.append("b.wilaya_code = ?")
        params.append(wilaya_code)
    if commune_id is not None:
        where.append("b.commune_id = ?")
        params.append(commune_id)
    if verification_status:
        where.append("b.verification_status = ?")
        params.append(verification_status)
    if needs_review_only:
        where.append("(b.verification_status = 'NEEDS_REVIEW' OR b.geo_uncertain = 1)")
    if source_key:
        where.append(
            "EXISTS (SELECT 1 FROM business_sources bs JOIN sources s ON s.id = bs.source_id WHERE bs.business_id = b.id AND s.key = ?)"
        )
        params.append(source_key)
    if has_phone is True:
        where.append("b.primary_phone != ''")
    elif has_phone is False:
        where.append("b.primary_phone = ''")
    if has_address is True:
        where.append("b.full_address != ''")
    elif has_address is False:
        where.append("b.full_address = ''")
    if has_website is True:
        where.append("b.website != ''")
    elif has_website is False:
        where.append("b.website = ''")
    if has_coords is True:
        where.append("b.lat IS NOT NULL AND b.lon IS NOT NULL")
    elif has_coords is False:
        where.append("(b.lat IS NULL OR b.lon IS NULL)")
    if date_from:
        where.append("b.first_collected_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("b.first_collected_at <= ?")
        params.append(date_to + "T23:59:59")

    allowed_sort = {
        "id": "b.id",
        "primary_name": "b.primary_name COLLATE NOCASE",
        "wilaya_code": "COALESCE(b.wilaya_code, 999)",
        "verification_status": "b.verification_status",
        "confidence_score": "b.confidence_score",
        "first_collected_at": "b.first_collected_at",
        "updated_at": "b.updated_at",
    }
    order_col = allowed_sort.get(sort_by, "b.updated_at")
    order_dir = "ASC" if sort_dir.lower() == "asc" else "DESC"
    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size

    with db_manager.read_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM businesses b WHERE {where_sql};", params).fetchone()["c"]
        rows = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT b.*, w.code_str AS wilaya_code_str, w.name_ar AS wilaya_name_ar,
                       (SELECT GROUP_CONCAT(DISTINCT s.key) FROM business_sources bs JOIN sources s ON s.id = bs.source_id WHERE bs.business_id = b.id) AS source_keys
                FROM businesses b
                LEFT JOIN wilayas w ON w.code = b.wilaya_code
                WHERE {where_sql}
                ORDER BY {order_col} {order_dir}
                LIMIT ? OFFSET ?;
                """,
                [*params, page_size, offset],
            ).fetchall()
        ]

    for r in rows:
        r["source_keys"] = r["source_keys"].split(",") if r.get("source_keys") else []
        r["other_socials"] = json.loads(r.get("other_socials_json") or "[]")

    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/businesses/{business_id}")
def get_business_detail(business_id: int) -> dict[str, Any]:
    with db_manager.read_connection() as conn:
        row = conn.execute(
            """
            SELECT b.*, w.code_str AS wilaya_code_str, w.name_ar AS wilaya_name_ar
            FROM businesses b
            LEFT JOIN wilayas w ON w.code = b.wilaya_code
            WHERE b.id = ?;
            """,
            (business_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Business not found")
        biz = dict(row)
        biz["other_socials"] = json.loads(biz.get("other_socials_json") or "[]")

        phones = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM phone_numbers WHERE business_id = ? ORDER BY is_primary DESC, id ASC;",
                (business_id,),
            ).fetchall()
        ]
        sources = [
            dict(r)
            for r in conn.execute(
                """
                SELECT sr.*, s.key AS source_key, s.name AS source_name, s.license_info
                FROM source_records sr
                JOIN sources s ON s.id = sr.source_id
                WHERE sr.business_id = ?
                ORDER BY sr.collected_at DESC;
                """,
                (business_id,),
            ).fetchall()
        ]
        verifications = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM verification_records WHERE business_id = ? ORDER BY verified_at DESC LIMIT 20;",
                (business_id,),
            ).fetchall()
        ]
        audits = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM audit_logs WHERE entity_type = 'business' AND entity_id = ? ORDER BY created_at DESC LIMIT 30;",
                (business_id,),
            ).fetchall()
        ]

    return {
        "business": biz,
        "phones": phones,
        "source_records": sources,
        "verification_records": verifications,
        "audit_logs": audits,
    }


@router.post("/businesses")
def create_business_manual(req: BusinessCreateRequest) -> dict[str, Any]:
    geo_svc = get_geography_service()
    w_name = geo_svc.wilayas[req.wilaya_code]["name_fr"] if req.wilaya_code and req.wilaya_code in geo_svc.wilayas else ""
    c_name = geo_svc.commune_by_id[req.commune_id]["name_fr"] if req.commune_id and req.commune_id in geo_svc.commune_by_id else ""
    rec = CollectedRawRecord(
        source_key="manual_import",
        external_id=f"manual_ui:{datetime.now(timezone.utc).timestamp()}",
        raw_name=req.primary_name,
        raw_name_ar=req.name_ar,
        raw_name_fr=req.name_fr,
        raw_name_en=req.name_en,
        raw_phones=[req.primary_phone] if req.primary_phone else [],
        raw_address=req.full_address,
        raw_commune=c_name,
        raw_wilaya=w_name,
        raw_lat=req.lat,
        raw_lon=req.lon,
        raw_website=req.website,
        raw_facebook=req.facebook_url,
        raw_instagram=req.instagram_url,
        raw_google_maps_url=req.google_maps_url,
        attribution_text="Manual Dashboard Entry",
        notes=req.notes,
    )
    with db_manager.transaction() as conn:
        outcome = ingest_raw_record(conn, rec, geo=geo_svc)
    return {"business_id": outcome.business_id, "action": outcome.action}


@router.patch("/businesses/{business_id}")
def update_business(business_id: int, req: BusinessUpdateRequest) -> dict[str, Any]:
    geo_svc = get_geography_service()
    now = datetime.now(timezone.utc).isoformat()
    with db_manager.transaction() as conn:
        row = conn.execute("SELECT * FROM businesses WHERE id = ?;", (business_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Business not found")
        before = dict(row)
        updates: dict[str, Any] = {}

        if req.primary_name is not None:
            updates["primary_name"] = req.primary_name.strip()
            updates["normalized_name"] = normalize_business_name(req.primary_name.strip())
        if req.name_ar is not None:
            updates["name_ar"] = req.name_ar.strip()
        if req.name_fr is not None:
            updates["name_fr"] = req.name_fr.strip()
        if req.name_en is not None:
            updates["name_en"] = req.name_en.strip()
        if req.full_address is not None:
            updates["full_address"] = req.full_address.strip()
        if req.website is not None:
            updates["website"] = normalize_url(req.website) if req.website.strip() else ""
        if req.facebook_url is not None:
            updates["facebook_url"] = normalize_url(req.facebook_url) if req.facebook_url.strip() else ""
        if req.instagram_url is not None:
            updates["instagram_url"] = normalize_url(req.instagram_url) if req.instagram_url.strip() else ""
        if req.google_maps_url is not None:
            updates["google_maps_url"] = normalize_url(req.google_maps_url) if req.google_maps_url.strip() else ""
        if req.notes is not None:
            updates["notes"] = req.notes

        if req.primary_phone is not None:
            raw_p = req.primary_phone.strip()
            if raw_p:
                parsed = normalize_algerian_phone(raw_p)
                updates["primary_phone"] = parsed.normalized_e164 or raw_p
                updates["primary_phone_raw"] = raw_p
                updates["primary_phone_status"] = parsed.validation_status
                conn.execute("UPDATE phone_numbers SET is_primary = 0 WHERE business_id = ?;", (business_id,))
                conn.execute(
                    """
                    INSERT INTO phone_numbers (
                        business_id, original_number, normalized_e164, national_format,
                        validation_status, number_type, carrier_hint, is_primary, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?);
                    """,
                    (
                        business_id,
                        parsed.original_number,
                        parsed.normalized_e164,
                        parsed.national_format,
                        parsed.validation_status,
                        parsed.number_type,
                        parsed.carrier_hint,
                        now,
                    ),
                )
            else:
                updates["primary_phone"] = ""
                updates["primary_phone_raw"] = ""
                updates["primary_phone_status"] = "unknown"

        if req.wilaya_code is not None:
            if req.wilaya_code not in geo_svc.wilayas:
                raise HTTPException(status_code=400, detail=f"Invalid wilaya code {req.wilaya_code}")
            updates["wilaya_code"] = req.wilaya_code
            updates["wilaya_name"] = geo_svc.wilayas[req.wilaya_code]["name_fr"]
            updates["geo_assignment_method"] = "manual"
            updates["geo_uncertain"] = 0

        if req.commune_id is not None:
            c = geo_svc.commune_by_id.get(req.commune_id)
            if not c:
                raise HTTPException(status_code=400, detail=f"Invalid commune id {req.commune_id}")
            updates["commune_id"] = req.commune_id
            updates["commune_name"] = c["name_fr"]
            if req.wilaya_code is None:
                updates["wilaya_code"] = int(c["wilaya_code"])
                updates["wilaya_name"] = geo_svc.wilayas[int(c["wilaya_code"])]["name_fr"]
            updates["geo_assignment_method"] = "manual"
            updates["geo_uncertain"] = 0

        if req.lat is not None or req.lon is not None:
            updates["lat"] = req.lat
            updates["lon"] = req.lon

        if req.verification_status is not None:
            updates["verification_status"] = req.verification_status
            updates["last_verified_at"] = now

        if updates:
            updates["updated_at"] = now
            set_sql = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(f"UPDATE businesses SET {set_sql} WHERE id = ?;", [*updates.values(), business_id])

        # Re-evaluate verification automatically unless status was explicitly overridden
        if req.verification_status is None:
            verify_and_persist(conn, business_id, geo=geo_svc, actor="manual_edit")

        after = dict(conn.execute("SELECT * FROM businesses WHERE id = ?;", (business_id,)).fetchone())
        conn.execute(
            """
            INSERT INTO manual_review_decisions (entity_type, entity_id, decision_type, notes, before_json, after_json, created_at)
            VALUES ('business', ?, 'manual_edit', ?, ?, ?, ?);
            """,
            (business_id, req.review_notes, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), now),
        )
        conn.execute(
            """
            INSERT INTO audit_logs (action, entity_type, entity_id, actor, details_json, created_at)
            VALUES ('manual_edit', 'business', ?, 'user', ?, ?);
            """,
            (business_id, json.dumps({"changed_fields": list(updates.keys()), "notes": req.review_notes}, ensure_ascii=False), now),
        )

    return {"updated": True, "business_id": business_id}


@router.post("/businesses/{business_id}/verify")
def verify_single_business(business_id: int, check_urls_online: bool = False) -> dict[str, Any]:
    with db_manager.transaction() as conn:
        ev = verify_and_persist(conn, business_id, check_urls_online=check_urls_online, actor="manual_trigger")
    return {
        "business_id": business_id,
        "status": ev.status,
        "confidence_score": ev.confidence_score,
        "checks": ev.checks,
        "notes": ev.notes,
    }


@router.post("/verification/run-batch")
def verify_batch(check_urls_online: bool = False) -> dict[str, Any]:
    geo_svc = get_geography_service()
    with db_manager.transaction() as conn:
        ids = [
            r["id"]
            for r in conn.execute("SELECT id FROM businesses WHERE is_merged = 0 ORDER BY id ASC;").fetchall()
        ]
        counts = {"VERIFIED": 0, "UNVERIFIED": 0, "NEEDS_REVIEW": 0, "CLOSED": 0}
        for bid in ids:
            ev = verify_and_persist(conn, bid, geo=geo_svc, check_urls_online=check_urls_online, actor="batch_verification")
            counts[ev.status] = counts.get(ev.status, 0) + 1
    return {"processed": len(ids), "status_breakdown": counts}


@router.get("/map/businesses")
def map_businesses(
    wilaya_code: int | None = None,
    verification_status: str = "",
    source_key: str = "",
) -> list[dict[str, Any]]:
    where = ["b.is_merged = 0", "b.lat IS NOT NULL", "b.lon IS NOT NULL"]
    params: list[Any] = []
    if wilaya_code is not None:
        where.append("b.wilaya_code = ?")
        params.append(wilaya_code)
    if verification_status:
        where.append("b.verification_status = ?")
        params.append(verification_status)
    if source_key:
        where.append(
            "EXISTS (SELECT 1 FROM business_sources bs JOIN sources s ON s.id = bs.source_id WHERE bs.business_id = b.id AND s.key = ?)"
        )
        params.append(source_key)

    with db_manager.read_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT b.id, b.primary_name, b.name_ar, b.primary_phone, b.full_address,
                   b.commune_name, b.wilaya_code, b.wilaya_name, b.lat, b.lon,
                   b.verification_status, b.confidence_score, b.website
            FROM businesses b
            WHERE {' AND '.join(where)}
            LIMIT 5000;
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/duplicates/candidates")
def list_duplicate_candidates(status: str = "pending") -> list[dict[str, Any]]:
    with db_manager.read_connection() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT dc.*
                FROM duplicate_candidates dc
                JOIN businesses ba ON ba.id = dc.business_a_id
                JOIN businesses bb ON bb.id = dc.business_b_id
                WHERE dc.status = ? AND ba.is_merged = 0 AND bb.is_merged = 0
                ORDER BY dc.overall_score DESC
                LIMIT 200;
                """,
                (status,),
            ).fetchall()
        ]
        result = []
        for r in rows:
            ba = dict(conn.execute("SELECT * FROM businesses WHERE id = ?;", (r["business_a_id"],)).fetchone())
            bb = dict(conn.execute("SELECT * FROM businesses WHERE id = ?;", (r["business_b_id"],)).fetchone())
            sa = [
                dict(s)
                for s in conn.execute(
                    "SELECT src.name, sr.source_url, sr.raw_address, sr.raw_phones_json FROM source_records sr JOIN sources src ON src.id = sr.source_id WHERE sr.business_id = ?;",
                    (ba["id"],),
                ).fetchall()
            ]
            sb = [
                dict(s)
                for s in conn.execute(
                    "SELECT src.name, sr.source_url, sr.raw_address, sr.raw_phones_json FROM source_records sr JOIN sources src ON src.id = sr.source_id WHERE sr.business_id = ?;",
                    (bb["id"],),
                ).fetchall()
            ]
            r["signals"] = json.loads(r["signals_json"] or "{}")
            r["business_a"] = {**ba, "sources": sa}
            r["business_b"] = {**bb, "sources": sb}
            result.append(r)
    return result


@router.post("/duplicates/candidates/{candidate_id}/resolve")
def resolve_duplicate_candidate(candidate_id: int, req: DuplicateResolveRequest) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with db_manager.transaction() as conn:
        cand = conn.execute("SELECT * FROM duplicate_candidates WHERE id = ?;", (candidate_id,)).fetchone()
        if not cand:
            raise HTTPException(status_code=404, detail="Duplicate candidate not found")
        a_id, b_id = int(cand["business_a_id"]), int(cand["business_b_id"])
        signals = json.loads(cand["signals_json"] or "{}")

        if req.decision == "reject_separate":
            conn.execute(
                "UPDATE duplicate_candidates SET status = 'rejected_separate', resolution_note = ?, resolved_at = ? WHERE id = ?;",
                (req.notes, now, candidate_id),
            )
            conn.execute(
                """
                INSERT INTO manual_review_decisions (entity_type, entity_id, decision_type, notes, created_at)
                VALUES ('duplicate_candidate', ?, 'rejected_separate', ?, ?);
                """,
                (candidate_id, req.notes, now),
            )
            return {"status": "rejected_separate"}

        target_id = a_id if req.decision == "merge_into_a" else b_id
        source_id = b_id if req.decision == "merge_into_a" else a_id
        merge_id = merge_businesses(
            conn,
            target_id=target_id,
            source_id=source_id,
            merge_type="manual",
            confidence_score=float(cand["overall_score"]),
            signals=signals,
            actor="user",
        )
        verify_and_persist(conn, target_id, actor="manual_merge")
        conn.execute(
            """
            INSERT INTO manual_review_decisions (entity_type, entity_id, decision_type, notes, created_at)
            VALUES ('duplicate_candidate', ?, ?, ?, ?);
            """,
            (candidate_id, req.decision, req.notes, now),
        )
        return {"status": "merged", "merge_id": merge_id, "target_business_id": target_id}


@router.post("/duplicates/scan")
def scan_duplicates() -> dict[str, Any]:
    """Scan active businesses by wilaya/phone to surface any missed duplicate candidates."""
    now = datetime.now(timezone.utc).isoformat()
    created = 0
    with db_manager.transaction() as conn:
        rows = [
            dict(r)
            for r in conn.execute("SELECT * FROM businesses WHERE is_merged = 0 ORDER BY id ASC;").fetchall()
        ]
        by_wilaya: dict[int, list[dict[str, Any]]] = {}
        for r in rows:
            if r.get("wilaya_code"):
                by_wilaya.setdefault(int(r["wilaya_code"]), []).append(r)

        phones_cache: dict[int, set[str]] = {}
        ext_cache: dict[int, set[str]] = {}
        for r in rows:
            bid = int(r["id"])
            phones_cache[bid] = {
                p["normalized_e164"]
                for p in conn.execute("SELECT normalized_e164 FROM phone_numbers WHERE business_id = ? AND normalized_e164 != '';", (bid,)).fetchall()
            }
            ext_cache[bid] = {
                s["external_id"]
                for s in conn.execute("SELECT external_id FROM source_records WHERE business_id = ? AND external_id != '';", (bid,)).fetchall()
            }

        for _, group in by_wilaya.items():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    aid, bid = int(a["id"]), int(b["id"])
                    ev = evaluate_duplicate_pair(
                        a,
                        b,
                        phones_a=phones_cache[aid],
                        phones_b=phones_cache[bid],
                        ext_ids_a=ext_cache[aid],
                        ext_ids_b=ext_cache[bid],
                    )
                    if ev.decision in ("auto_merge", "review"):
                        cur = conn.execute(
                            """
                            INSERT OR IGNORE INTO duplicate_candidates (
                                business_a_id, business_b_id, overall_score, signals_json, status, created_at
                            ) VALUES (?, ?, ?, ?, 'pending', ?);
                            """,
                            (min(aid, bid), max(aid, bid), ev.score, json.dumps(ev.signals, ensure_ascii=False), now),
                        )
                        if cur.rowcount > 0:
                            created += 1
    return {"new_candidates_created": created}


@router.get("/merges/history")
def list_merge_history() -> list[dict[str, Any]]:
    with db_manager.read_connection() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT mh.id, mh.target_business_id, mh.source_business_id, mh.merge_type,
                       mh.confidence_score, mh.signals_json, mh.is_reverted, mh.reverted_at, mh.created_at,
                       bt.primary_name AS target_name,
                       bs.primary_name AS source_name
                FROM merge_history mh
                JOIN businesses bt ON bt.id = mh.target_business_id
                JOIN businesses bs ON bs.id = mh.source_business_id
                ORDER BY mh.id DESC
                LIMIT 200;
                """
            ).fetchall()
        ]
    for r in rows:
        r["signals"] = json.loads(r["signals_json"] or "{}")
    return rows


@router.post("/merges/{merge_id}/revert")
def revert_merge_endpoint(merge_id: int) -> dict[str, Any]:
    with db_manager.transaction() as conn:
        try:
            res = revert_merge(conn, merge_id, actor="user")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return res


@router.get("/sources")
def list_sources() -> list[dict[str, Any]]:
    with db_manager.read_connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM sources ORDER BY id ASC;").fetchall()]
    pbf_path = safe_resolve_within(settings.raw_dir, "algeria-latest.osm.pbf")
    for r in rows:
        r["config"] = json.loads(r.get("config_json") or "{}")
        if r["key"] == "osm_pbf":
            r["pbf_local_exists"] = pbf_path.exists()
            r["pbf_local_size_mb"] = round(pbf_path.stat().st_size / (1024 * 1024), 1) if pbf_path.exists() else 0.0
            r["pbf_download_state"] = dict(_pbf_download_state)
    return rows


@router.patch("/sources/{key}")
def update_source(key: str, req: SourceUpdateRequest) -> dict[str, Any]:
    with db_manager.transaction() as conn:
        row = conn.execute("SELECT * FROM sources WHERE key = ?;", (key,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")
        updates: dict[str, Any] = {}
        if req.enabled is not None:
            updates["enabled"] = 1 if req.enabled else 0
        if req.rate_limit_seconds is not None:
            updates["rate_limit_seconds"] = req.rate_limit_seconds
        if req.max_retries is not None:
            updates["max_retries"] = req.max_retries
        if req.config is not None:
            merged = {**json.loads(row["config_json"] or "{}"), **req.config}
            updates["config_json"] = json.dumps(merged, ensure_ascii=False)
        if updates:
            set_sql = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(f"UPDATE sources SET {set_sql} WHERE key = ?;", [*updates.values(), key])
    return {"updated": True, "key": key}


@router.post("/sources/{key}/test")
def test_source(key: str) -> dict[str, Any]:
    if key == "manual_import":
        return {"ok": True, "message": "Manual CSV/XLSX/GeoJSON import is ready."}
    adapter = ADAPTER_REGISTRY.get(key)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Unknown source '{key}'")
    return adapter.test_connection()


@router.post("/sources/osm-pbf/download")
def trigger_pbf_download() -> dict[str, Any]:
    if _pbf_download_state["downloading"]:
        return {"started": False, "state": dict(_pbf_download_state)}

    def _worker() -> None:
        _pbf_download_state.update({"downloading": True, "error": "", "completed": False, "downloaded_bytes": 0, "total_bytes": 0})
        try:
            def _cb(done: int, total: int) -> None:
                _pbf_download_state["downloaded_bytes"] = done
                _pbf_download_state["total_bytes"] = total

            download_algeria_pbf(progress_cb=_cb)
            _pbf_download_state["completed"] = True
        except Exception as exc:
            _pbf_download_state["error"] = str(exc)
        finally:
            _pbf_download_state["downloading"] = False

    threading.Thread(target=_worker, daemon=True, name="pbf-downloader").start()
    return {"started": True, "state": dict(_pbf_download_state)}


@router.post("/imports/upload")
async def upload_manual_import(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    safe_name = Path(file.filename).name
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Import file exceeds 25 MB limit")

    try:
        records = parse_manual_import_bytes(content, safe_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    geo_svc = get_geography_service()
    summary = {"total_rows": len(records), "new": 0, "auto_merged": 0, "review_candidate": 0, "rejected": 0}
    with db_manager.transaction() as conn:
        for rec in records:
            out = ingest_raw_record(conn, rec, geo=geo_svc)
            if out.action in summary:
                summary[out.action] += 1
        conn.execute(
            "UPDATE sources SET last_run_at = ?, last_status = 'ok' WHERE key = 'manual_import';",
            (datetime.now(timezone.utc).isoformat(),),
        )
    return summary


@router.post("/collections/start")
def start_collection(req: CollectionStartRequest) -> dict[str, Any]:
    try:
        run_id = collection_engine.start_run(
            wilaya_codes=req.wilaya_codes or None,
            commune_ids=req.commune_ids or None,
            source_keys=req.source_keys or None,
            search_depth=req.search_depth,
            notes=req.notes,
        )
        return {"run_id": run_id, "status": "running"}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/collections/{run_id}/stop")
def stop_collection(run_id: int) -> dict[str, Any]:
    return collection_engine.stop_run(run_id)


@router.post("/collections/{run_id}/resume")
def resume_collection(run_id: int) -> dict[str, Any]:
    try:
        resumed = collection_engine.resume_run(run_id)
        return {"run_id": resumed, "status": "running"}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/collections")
def list_collections() -> list[dict[str, Any]]:
    with db_manager.read_connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM collection_runs ORDER BY id DESC LIMIT 50;").fetchall()]
    for r in rows:
        r["selected_wilayas"] = json.loads(r["selected_wilayas_json"] or "[]")
        r["selected_sources"] = json.loads(r["selected_sources_json"] or "[]")
    return rows


@router.get("/collections/{run_id}")
def get_collection_detail(run_id: int) -> dict[str, Any]:
    with db_manager.read_connection() as conn:
        run = conn.execute("SELECT * FROM collection_runs WHERE id = ?;", (run_id,)).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Collection run not found")
        progress = [
            dict(r)
            for r in conn.execute(
                """
                SELECT p.*, w.code_str, w.name_fr, w.name_ar
                FROM collection_wilaya_progress p
                JOIN wilayas w ON w.code = p.wilaya_code
                WHERE p.run_id = ?
                ORDER BY p.wilaya_code ASC, p.source_key ASC;
                """,
                (run_id,),
            ).fetchall()
        ]
    run_d = dict(run)
    run_d["selected_wilayas"] = json.loads(run_d["selected_wilayas_json"] or "[]")
    run_d["selected_sources"] = json.loads(run_d["selected_sources_json"] or "[]")
    return {"run": run_d, "wilaya_progress": progress, "is_actively_running": collection_engine.get_active_run_id() == run_id}


@router.post("/exports")
def create_export(req: ExportCreateRequest) -> dict[str, Any]:
    with db_manager.read_connection() as conn:
        if req.format == "xlsx":
            out_path = export_excel(
                conn,
                scope=req.scope,
                wilaya_codes=req.wilaya_codes or None,
                business_ids=req.business_ids or None,
            )
        else:
            out_path = export_csv(
                conn,
                scope=req.scope,
                wilaya_codes=req.wilaya_codes or None,
                business_ids=req.business_ids or None,
            )
    return {
        "filename": out_path.name,
        "format": req.format,
        "size_bytes": out_path.stat().st_size,
        "download_url": f"/api/exports/download/{out_path.name}",
    }


@router.get("/exports")
def list_exports() -> list[dict[str, Any]]:
    items = []
    for p in sorted(settings.exports_dir.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True):
        if p.suffix.lower() not in (".xlsx", ".csv"):
            continue
        st = p.stat()
        items.append(
            {
                "filename": p.name,
                "format": p.suffix.lstrip(".").lower(),
                "size_bytes": st.st_size,
                "created_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "download_url": f"/api/exports/download/{p.name}",
            }
        )
    return items


@router.get("/exports/download/{filename}")
def download_export(filename: str) -> FileResponse:
    try:
        target = safe_resolve_within(settings.exports_dir, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    media = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if target.suffix.lower() == ".xlsx"
        else "text/csv; charset=utf-8"
    )
    return FileResponse(path=str(target), filename=target.name, media_type=media)


@router.get("/logs")
def get_app_logs(level: str = "", limit: int = Query(200, ge=1, le=1000)) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if level:
        where.append("level = ?")
        params.append(level.upper())
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with db_manager.read_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM app_logs {where_sql} ORDER BY id DESC LIMIT ?;",
            [*params, limit],
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/audit-logs")
def get_audit_logs(limit: int = Query(200, ge=1, le=1000)) -> list[dict[str, Any]]:
    with db_manager.read_connection() as conn:
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?;", (limit,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    with db_manager.read_connection() as conn:
        rows = conn.execute("SELECT key, value_json, updated_at FROM app_settings;").fetchall()
    return {r["key"]: json.loads(r["value_json"]) for r in rows}


@router.patch("/settings")
def update_settings(req: SettingsUpdateRequest) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with db_manager.transaction() as conn:
        for key, val in req.settings.items():
            conn.execute(
                """
                INSERT INTO app_settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at;
                """,
                (key, json.dumps(val, ensure_ascii=False), now),
            )
    return get_settings()


@router.get("/backups")
def list_backups() -> list[dict[str, Any]]:
    return db_manager.list_backups()


@router.post("/backups/create")
def create_backup() -> dict[str, Any]:
    path = db_manager.create_backup(reason="manual")
    if not path:
        raise HTTPException(status_code=400, detail="Database file does not exist yet")
    return {"filename": path.name, "size_bytes": path.stat().st_size}


@router.post("/backups/restore")
def restore_backup(req: RestoreBackupRequest) -> dict[str, Any]:
    if collection_engine.is_running():
        raise HTTPException(status_code=409, detail="Stop active collection run before restoring database")
    try:
        db_manager.restore_backup(req.filename)
        return {"restored": True, "filename": req.filename}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/database/integrity")
def check_database_integrity() -> dict[str, Any]:
    return db_manager.integrity_check()
