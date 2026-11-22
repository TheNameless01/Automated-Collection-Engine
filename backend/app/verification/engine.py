"""Evidence-based automatic verification and confidence scoring engine."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.geography.service import GeographyService, get_geography_service
from app.processors.phone_processor import normalize_algerian_phone
from app.processors.text_normalizer import is_valid_http_url


@dataclass
class VerificationEvaluation:
    status: str  # VERIFIED | UNVERIFIED | NEEDS_REVIEW | CLOSED
    confidence_score: float
    checks: dict[str, Any]
    supporting_sources_count: int
    notes: str


def check_url_reachable(url: str, timeout_seconds: float = 6.0) -> tuple[bool | None, str]:
    if not is_valid_http_url(url):
        return False, "invalid_syntax"
    try:
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        ) as client:
            resp = client.head(url)
            if resp.status_code == 405:
                resp = client.get(url)
            if 200 <= resp.status_code < 400:
                return True, f"http_{resp.status_code}"
            return False, f"http_{resp.status_code}"
    except Exception as exc:
        # Temporary network errors must NEVER classify a business as CLOSED
        return None, f"unreachable_temp:{type(exc).__name__}"


def evaluate_business_verification(
    conn: sqlite3.Connection,
    business_id: int,
    *,
    geo: GeographyService | None = None,
    check_urls_online: bool = False,
) -> VerificationEvaluation:
    geo_svc = geo or get_geography_service()
    biz = conn.execute("SELECT * FROM businesses WHERE id = ?;", (business_id,)).fetchone()
    if not biz:
        raise ValueError(f"Business {business_id} not found")
    b = dict(biz)

    # Preserve manual CLOSED status unless user explicitly reopens
    if b["verification_status"] == "CLOSED":
        return VerificationEvaluation(
            status="CLOSED",
            confidence_score=float(b["confidence_score"] or 0.0),
            checks={"manual_closed": True},
            supporting_sources_count=0,
            notes="Marked as CLOSED.",
        )

    phones = [
        dict(r)
        for r in conn.execute("SELECT * FROM phone_numbers WHERE business_id = ?;", (business_id,)).fetchall()
    ]
    sources = [
        dict(r)
        for r in conn.execute(
            """
            SELECT bs.*, s.key AS source_key, sr.raw_wilaya, sr.raw_phones_json
            FROM business_sources bs
            JOIN sources s ON s.id = bs.source_id
            JOIN source_records sr ON sr.id = bs.source_record_id
            WHERE bs.business_id = ?;
            """,
            (business_id,),
        ).fetchall()
    ]
    distinct_sources = {s["source_key"] for s in sources}

    has_name = bool((b.get("primary_name") or "").strip()) and len((b.get("primary_name") or "").strip()) >= 2

    # Phone format validity
    valid_phones = [p for p in phones if p["validation_status"] in ("valid_format", "verified_reachable")]
    invalid_phones = [p for p in phones if p["validation_status"] == "invalid_format"]
    if not valid_phones and b.get("primary_phone"):
        parsed_p = normalize_algerian_phone(b["primary_phone"])
        phone_valid = parsed_p.validation_status == "valid_format"
    else:
        phone_valid = len(valid_phones) > 0

    # Address plausibility
    addr = (b.get("full_address") or "").strip()
    address_plausible = len(addr) >= 5 and addr.lower() not in {"n/a", "na", "none", "unknown", "-"}

    # Geography checks
    wilaya_assigned = b.get("wilaya_code") is not None
    commune_valid = geo_svc.commune_belongs_to_wilaya(b.get("commune_id"), b.get("wilaya_code"))
    has_coords = b.get("lat") is not None and b.get("lon") is not None
    in_algeria = geo_svc.is_in_algeria(float(b["lat"]), float(b["lon"])) if has_coords else None

    # Website check
    website = (b.get("website") or "").strip()
    website_syntax_ok = is_valid_http_url(website) if website else None
    website_reach_info = None
    if website and check_urls_online and website_syntax_ok:
        ok, detail = check_url_reachable(website)
        website_reach_info = {"reachable": ok, "detail": detail}

    # Conflict checks across supporting source records
    raw_wilayas = {
        geo_svc.match_wilaya_text(s["raw_wilaya"])
        for s in sources
        if s.get("raw_wilaya") and geo_svc.match_wilaya_text(s["raw_wilaya"]) is not None
    }
    wilaya_conflict = len(raw_wilayas) > 1

    checks = {
        "has_name": has_name,
        "phone_valid_format": phone_valid,
        "invalid_phone_count": len(invalid_phones),
        "address_plausible": address_plausible,
        "wilaya_assigned": wilaya_assigned,
        "commune_belongs_to_wilaya": commune_valid,
        "has_coords": has_coords,
        "coords_in_algeria": in_algeria,
        "geo_uncertain": bool(b.get("geo_uncertain")),
        "website_syntax_ok": website_syntax_ok,
        "website_reachability": website_reach_info,
        "wilaya_conflict": wilaya_conflict,
        "supporting_sources": sorted(distinct_sources),
    }

    # Confidence scoring (never 1.0 by mere discovery)
    score = 0.0
    if has_name:
        score += 0.15
    if phone_valid:
        score += 0.25
    if address_plausible:
        score += 0.12
    if wilaya_assigned and not b.get("geo_uncertain"):
        score += 0.12
    elif wilaya_assigned:
        score += 0.05
    if commune_valid is True:
        score += 0.06
    if in_algeria is True:
        score += 0.15
    if website_syntax_ok is True:
        score += 0.05
        if website_reach_info and website_reach_info.get("reachable") is True:
            score += 0.05
    if len(distinct_sources) >= 2:
        score += 0.15
    elif len(sources) >= 2:
        score += 0.06

    if in_algeria is False or commune_valid is False or wilaya_conflict or (website and website_syntax_ok is False):
        score -= 0.20
    if invalid_phones and not valid_phones:
        score -= 0.10

    score = max(0.0, min(1.0, round(score, 3)))

    notes: list[str] = []
    review_reasons: list[str] = []

    if not has_name:
        review_reasons.append("Missing business name")
    if in_algeria is False:
        review_reasons.append("GPS coordinates fall outside Algeria")
    if commune_valid is False:
        review_reasons.append("Assigned commune does not belong to assigned wilaya")
    if b.get("geo_uncertain"):
        review_reasons.append("Uncertain wilaya/boundary assignment")
    if wilaya_conflict:
        review_reasons.append("Conflicting wilaya information across sources")
    if website and website_syntax_ok is False:
        review_reasons.append("Invalid website URL syntax")
    if invalid_phones and not valid_phones:
        review_reasons.append("Invalid Algerian phone format")

    # Status assignment rules: never mark VERIFIED merely because discovered
    if review_reasons:
        status = "NEEDS_REVIEW"
        notes.extend(review_reasons)
    elif (
        score >= 0.78
        and has_name
        and phone_valid
        and wilaya_assigned
        and (len(distinct_sources) >= 2 or (in_algeria is True and address_plausible))
    ):
        status = "VERIFIED"
        notes.append("Verified by multi-signal evidence and geographic/contact checks.")
    else:
        status = "UNVERIFIED"
        if not phone_valid:
            notes.append("Missing or unvalidated phone number.")
        if not has_coords:
            notes.append("No GPS coordinates yet.")
        if len(distinct_sources) < 2:
            notes.append("Single-source record awaiting corroboration or richer evidence.")

    return VerificationEvaluation(
        status=status,
        confidence_score=score,
        checks=checks,
        supporting_sources_count=len(distinct_sources),
        notes=" ".join(notes),
    )


def verify_and_persist(
    conn: sqlite3.Connection,
    business_id: int,
    *,
    geo: GeographyService | None = None,
    check_urls_online: bool = False,
    actor: str = "system",
) -> VerificationEvaluation:
    row = conn.execute("SELECT verification_status FROM businesses WHERE id = ?;", (business_id,)).fetchone()
    prev_status = row["verification_status"] if row else "UNVERIFIED"
    ev = evaluate_business_verification(conn, business_id, geo=geo, check_urls_online=check_urls_online)
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        UPDATE businesses
        SET verification_status = ?, confidence_score = ?, verification_notes = ?,
            last_verified_at = ?, updated_at = ?
        WHERE id = ?;
        """,
        (ev.status, ev.confidence_score, ev.notes, now, now, business_id),
    )
    conn.execute(
        """
        INSERT INTO verification_records (
            business_id, previous_status, new_status, verification_method,
            confidence_score, checks_json, supporting_sources_count, notes, verified_by, verified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            business_id,
            prev_status,
            ev.status,
            "automatic_evidence_rules" + ("+http_head" if check_urls_online else ""),
            ev.confidence_score,
            json.dumps(ev.checks, ensure_ascii=False),
            ev.supporting_sources_count,
            ev.notes,
            actor,
            now,
        ),
    )
    return ev
