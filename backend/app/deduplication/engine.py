"""Weighted multi-signal deduplication and reversible merge engine."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from rapidfuzz import fuzz

from app.geography.service import haversine_km
from app.processors.text_normalizer import (
    extract_branch_markers,
    extract_domain,
    normalize_arabic,
    normalize_latin,
    normalize_social_handle,
    phonetic_latin_key,
    strip_business_boilerplate,
    transliterate_ar_to_latin,
)

SOCIAL_DOMAINS = {"facebook.com", "fb.com", "instagram.com", "linkedin.com", "tiktok.com", "youtube.com", "x.com", "twitter.com"}


@dataclass
class MatchEvaluation:
    score: float
    decision: str  # auto_merge | review | separate
    signals: dict[str, Any]
    reason: str


def _name_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    names_a = [a.get("primary_name", ""), a.get("name_fr", ""), a.get("name_ar", ""), a.get("name_en", "")]
    names_b = [b.get("primary_name", ""), b.get("name_fr", ""), b.get("name_ar", ""), b.get("name_en", "")]

    best = 0.0
    for na in names_a:
        if not na:
            continue
        for nb in names_b:
            if not nb:
                continue
            sa = strip_business_boilerplate(na)
            sb = strip_business_boilerplate(nb)
            if not sa or not sb:
                continue
            # Direct same-script match
            score = fuzz.token_sort_ratio(sa, sb) / 100.0
            if score > best:
                best = score
            # Cross-script Arabic <-> Latin transliteration & phonetic match
            ta = transliterate_ar_to_latin(sa) if any("\u0600" <= c <= "\u06FF" for c in sa) else sa
            tb = transliterate_ar_to_latin(sb) if any("\u0600" <= c <= "\u06FF" for c in sb) else sb
            if ta and tb:
                cross = fuzz.token_sort_ratio(ta, tb) / 100.0
                pa = phonetic_latin_key(ta)
                pb = phonetic_latin_key(tb)
                if pa and pb:
                    phon = fuzz.token_sort_ratio(pa, pb) / 100.0
                    cross = max(cross, phon)
                if cross * 0.92 > best:
                    best = cross * 0.92
    return round(best, 4)


def _address_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    addr_a = normalize_latin(a.get("full_address", "")) or normalize_arabic(a.get("full_address", ""))
    addr_b = normalize_latin(b.get("full_address", "")) or normalize_arabic(b.get("full_address", ""))
    if not addr_a or not addr_b:
        return 0.0
    return round(fuzz.token_sort_ratio(addr_a, addr_b) / 100.0, 4)


def evaluate_duplicate_pair(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    phones_a: set[str],
    phones_b: set[str],
    ext_ids_a: set[str],
    ext_ids_b: set[str],
    auto_merge_threshold: float = 0.88,
    review_threshold: float = 0.58,
    max_branch_distance_km: float = 1.5,
) -> MatchEvaluation:
    """Compute weighted duplicate likelihood with strict branch & single-phone guards."""
    signals: dict[str, Any] = {}

    # 1. Exact stable external ID overlap (e.g. osm:node/12345)
    shared_ext = ext_ids_a & ext_ids_b
    if shared_ext:
        return MatchEvaluation(
            score=1.0,
            decision="auto_merge",
            signals={"shared_external_ids": sorted(shared_ext)},
            reason="Identical stable external source identifier.",
        )

    # 2. Phone overlap
    shared_phones = {p for p in (phones_a & phones_b) if p}
    signals["shared_phones"] = sorted(shared_phones)

    # 3. Name & address similarity
    name_sim = _name_similarity(a, b)
    addr_sim = _address_similarity(a, b)
    signals["name_similarity"] = name_sim
    signals["address_similarity"] = addr_sim

    # 4. Geographic proximity
    dist_km: float | None = None
    if a.get("lat") is not None and a.get("lon") is not None and b.get("lat") is not None and b.get("lon") is not None:
        dist_km = round(haversine_km(float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"])), 3)
    signals["distance_km"] = dist_km

    same_wilaya = (
        a.get("wilaya_code") is not None
        and b.get("wilaya_code") is not None
        and int(a["wilaya_code"]) == int(b["wilaya_code"])
    )
    different_wilaya = (
        a.get("wilaya_code") is not None
        and b.get("wilaya_code") is not None
        and int(a["wilaya_code"]) != int(b["wilaya_code"])
    )
    same_commune = (
        a.get("commune_id") is not None
        and b.get("commune_id") is not None
        and int(a["commune_id"]) == int(b["commune_id"])
    )
    different_commune = (
        a.get("commune_id") is not None
        and b.get("commune_id") is not None
        and int(a["commune_id"]) != int(b["commune_id"])
    )
    signals["same_wilaya"] = same_wilaya
    signals["same_commune"] = same_commune

    # 5. Website domain & social media match
    dom_a = extract_domain(a.get("website", ""))
    dom_b = extract_domain(b.get("website", ""))
    shared_domain = bool(dom_a and dom_b and dom_a == dom_b and dom_a not in SOCIAL_DOMAINS)
    signals["shared_domain"] = dom_a if shared_domain else ""

    fb_a = normalize_social_handle(a.get("facebook_url", ""), "facebook")
    fb_b = normalize_social_handle(b.get("facebook_url", ""), "facebook")
    ig_a = normalize_social_handle(a.get("instagram_url", ""), "instagram")
    ig_b = normalize_social_handle(b.get("instagram_url", ""), "instagram")
    shared_social = bool((fb_a and fb_a == fb_b) or (ig_a and ig_a == ig_b))
    signals["shared_social"] = shared_social

    # Branch / distinct location detection
    branch_markers_a = extract_branch_markers(a.get("primary_name", ""))
    branch_markers_b = extract_branch_markers(b.get("primary_name", ""))
    distinct_branch_markers = bool(
        branch_markers_a and branch_markers_b and branch_markers_a != branch_markers_b
    )
    far_apart = (dist_km is not None and dist_km > max_branch_distance_km) or different_wilaya or (
        different_commune and addr_sim < 0.45 and (dist_km is None or dist_km > max_branch_distance_km)
    )
    signals["branch_guard_triggered"] = distinct_branch_markers or far_apart

    # Weighted score
    score = 0.0
    score += 0.36 * name_sim
    if shared_phones:
        score += 0.30
    if shared_domain:
        score += 0.14
    if shared_social:
        score += 0.12
    score += 0.18 * addr_sim

    if dist_km is not None:
        if dist_km <= 0.15:
            score += 0.18
        elif dist_km <= 0.5:
            score += 0.10
        elif dist_km > 3.0:
            score -= 0.20

    if same_commune:
        score += 0.05
    elif different_wilaya:
        score -= 0.25

    score = max(0.0, min(1.0, round(score, 4)))

    # Rule: A shared phone number alone must NOT be sufficient evidence for auto-merging.
    supporting_non_phone = (
        name_sim >= 0.72
        or addr_sim >= 0.70
        or (dist_km is not None and dist_km <= 0.35)
        or shared_domain
        or shared_social
    )

    # Rule: Two branches of the same company must NOT automatically become one business.
    if signals["branch_guard_triggered"]:
        if score >= review_threshold or shared_phones or (name_sim >= 0.85 and same_wilaya):
            return MatchEvaluation(
                score=min(score, auto_merge_threshold - 0.05),
                decision="review",
                signals=signals,
                reason="Potential branch or distinct location of same brand — routed to manual review.",
            )
        return MatchEvaluation(
            score=score,
            decision="separate",
            signals=signals,
            reason="Distinct locations/branches kept separate.",
        )

    if shared_phones and not supporting_non_phone:
        return MatchEvaluation(
            score=min(score, 0.72),
            decision="review",
            signals=signals,
            reason="Shared phone number without corroborating name/address/location evidence.",
        )

    if score >= auto_merge_threshold and (shared_phones or name_sim >= 0.88 or shared_domain or (dist_km is not None and dist_km <= 0.15 and name_sim >= 0.75)):
        return MatchEvaluation(
            score=score,
            decision="auto_merge",
            signals=signals,
            reason="High-confidence multi-signal duplicate.",
        )

    if score >= review_threshold:
        return MatchEvaluation(
            score=score,
            decision="review",
            signals=signals,
            reason="Moderate similarity — requires manual comparison.",
        )

    return MatchEvaluation(
        score=score,
        decision="separate",
        signals=signals,
        reason="Insufficient similarity; kept separate.",
    )


def merge_businesses(
    conn: sqlite3.Connection,
    *,
    target_id: int,
    source_id: int,
    merge_type: str,
    confidence_score: float,
    signals: dict[str, Any],
    actor: str = "system",
) -> int:
    """Safely merge source_id into target_id while preserving full reversible snapshot."""
    if target_id == source_id:
        raise ValueError("Cannot merge a business into itself")

    target_row = conn.execute("SELECT * FROM businesses WHERE id = ? AND is_merged = 0;", (target_id,)).fetchone()
    source_row = conn.execute("SELECT * FROM businesses WHERE id = ? AND is_merged = 0;", (source_id,)).fetchone()
    if not target_row or not source_row:
        raise ValueError("Both target and source businesses must exist and be unmerged")

    target_before = dict(target_row)
    source_snapshot = dict(source_row)
    now = datetime.now(timezone.utc).isoformat()

    # Fill empty fields on target from source without overwriting existing user/target facts
    merged_fields: dict[str, Any] = {}
    for col in (
        "name_ar",
        "name_fr",
        "name_en",
        "primary_phone",
        "primary_phone_raw",
        "full_address",
        "website",
        "facebook_url",
        "instagram_url",
        "google_maps_url",
        "commune_name",
        "wilaya_name",
    ):
        if not target_before.get(col) and source_snapshot.get(col):
            merged_fields[col] = source_snapshot[col]
            if col == "primary_phone":
                merged_fields["primary_phone_status"] = source_snapshot.get("primary_phone_status", "unknown")

    if target_before.get("wilaya_code") is None and source_snapshot.get("wilaya_code") is not None:
        merged_fields["wilaya_code"] = source_snapshot["wilaya_code"]
        merged_fields["wilaya_name"] = source_snapshot.get("wilaya_name", "")
    if target_before.get("commune_id") is None and source_snapshot.get("commune_id") is not None:
        merged_fields["commune_id"] = source_snapshot["commune_id"]
        merged_fields["commune_name"] = source_snapshot.get("commune_name", "")
    if target_before.get("lat") is None and source_snapshot.get("lat") is not None:
        merged_fields["lat"] = source_snapshot["lat"]
        merged_fields["lon"] = source_snapshot["lon"]
        merged_fields["geo_assignment_method"] = source_snapshot.get("geo_assignment_method", "unknown")
        merged_fields["geo_uncertain"] = source_snapshot.get("geo_uncertain", 0)

    # Combine other_socials_json
    socials_t = set(json.loads(target_before.get("other_socials_json") or "[]"))
    socials_s = set(json.loads(source_snapshot.get("other_socials_json") or "[]"))
    combined_socials = sorted(socials_t | socials_s)
    if combined_socials:
        merged_fields["other_socials_json"] = json.dumps(combined_socials, ensure_ascii=False)

    # Combine notes
    if source_snapshot.get("notes") and source_snapshot["notes"] not in (target_before.get("notes") or ""):
        existing_note = (target_before.get("notes") or "").strip()
        merged_fields["notes"] = (existing_note + "\n" + source_snapshot["notes"]).strip()

    # Keep earliest first_collected_at and latest last_collected_at
    if source_snapshot["first_collected_at"] < target_before["first_collected_at"]:
        merged_fields["first_collected_at"] = source_snapshot["first_collected_at"]
    if source_snapshot["last_collected_at"] > target_before["last_collected_at"]:
        merged_fields["last_collected_at"] = source_snapshot["last_collected_at"]

    merged_fields["updated_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in merged_fields)
    conn.execute(
        f"UPDATE businesses SET {set_clause} WHERE id = ?;",
        [*merged_fields.values(), target_id],
    )

    # Move source_records, business_sources, phone_numbers, business_names, addresses, geographic_locations
    moved_sr_ids = [
        r["id"] for r in conn.execute("SELECT id FROM source_records WHERE business_id = ?;", (source_id,)).fetchall()
    ]
    conn.execute("UPDATE source_records SET business_id = ? WHERE business_id = ?;", (target_id, source_id))
    conn.execute("UPDATE OR IGNORE business_sources SET business_id = ? WHERE business_id = ?;", (target_id, source_id))

    moved_phone_ids = [
        r["id"] for r in conn.execute("SELECT id FROM phone_numbers WHERE business_id = ?;", (source_id,)).fetchall()
    ]
    conn.execute("UPDATE phone_numbers SET business_id = ?, is_primary = 0 WHERE business_id = ?;", (target_id, source_id))
    conn.execute("UPDATE business_names SET business_id = ?, is_primary = 0 WHERE business_id = ?;", (target_id, source_id))
    conn.execute("UPDATE addresses SET business_id = ?, is_primary = 0 WHERE business_id = ?;", (target_id, source_id))
    conn.execute("UPDATE geographic_locations SET business_id = ? WHERE business_id = ?;", (target_id, source_id))

    # Mark source business as merged (never delete evidence)
    conn.execute(
        "UPDATE businesses SET is_merged = 1, merged_into_id = ?, updated_at = ? WHERE id = ?;",
        (target_id, now, source_id),
    )

    # Resolve any pending duplicate candidates involving source_id
    conn.execute(
        """
        UPDATE duplicate_candidates
        SET status = ?, resolved_at = ?, resolution_note = ?
        WHERE status = 'pending' AND ((business_a_id = ? AND business_b_id = ?) OR (business_a_id = ? AND business_b_id = ?));
        """,
        (
            "auto_merged" if merge_type == "auto" else "approved_merge",
            now,
            f"Merged {source_id} into {target_id}",
            min(target_id, source_id),
            max(target_id, source_id),
            max(target_id, source_id),
            min(target_id, source_id),
        ),
    )

    cur = conn.execute(
        """
        INSERT INTO merge_history (
            target_business_id, source_business_id, merge_type, confidence_score,
            signals_json, source_snapshot_json, target_before_snapshot_json,
            moved_source_record_ids_json, moved_phone_ids_json, is_reverted, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?);
        """,
        (
            target_id,
            source_id,
            merge_type,
            confidence_score,
            json.dumps(signals, ensure_ascii=False),
            json.dumps(source_snapshot, ensure_ascii=False),
            json.dumps(target_before, ensure_ascii=False),
            json.dumps(moved_sr_ids),
            json.dumps(moved_phone_ids),
            now,
        ),
    )
    merge_id = int(cur.lastrowid)

    conn.execute(
        """
        INSERT INTO audit_logs (action, entity_type, entity_id, actor, details_json, created_at)
        VALUES (?, 'business', ?, ?, ?, ?);
        """,
        (
            f"merge_{merge_type}",
            target_id,
            actor,
            json.dumps({"merge_id": merge_id, "source_business_id": source_id, "confidence_score": confidence_score}),
            now,
        ),
    )
    return merge_id


def revert_merge(conn: sqlite3.Connection, merge_id: int, actor: str = "user") -> dict[str, Any]:
    """Reverse an automatic or manual merge, restoring original businesses and source links."""
    mh = conn.execute("SELECT * FROM merge_history WHERE id = ?;", (merge_id,)).fetchone()
    if not mh:
        raise ValueError(f"Merge history {merge_id} not found")
    if mh["is_reverted"]:
        raise ValueError(f"Merge {merge_id} has already been reverted")

    target_id = int(mh["target_business_id"])
    source_id = int(mh["source_business_id"])
    target_before = json.loads(mh["target_before_snapshot_json"])
    source_snap = json.loads(mh["source_snapshot_json"])
    moved_sr_ids = json.loads(mh["moved_source_record_ids_json"])
    moved_phone_ids = json.loads(mh["moved_phone_ids_json"])
    now = datetime.now(timezone.utc).isoformat()

    # Restore source business active flag & fields
    conn.execute(
        """
        UPDATE businesses
        SET is_merged = 0, merged_into_id = NULL, updated_at = ?
        WHERE id = ?;
        """,
        (now, source_id),
    )

    # Restore target business pre-merge snapshot fields
    restore_cols = [
        "name_ar", "name_fr", "name_en", "primary_phone", "primary_phone_raw", "primary_phone_status",
        "full_address", "commune_id", "commune_name", "wilaya_code", "wilaya_name",
        "lat", "lon", "geo_assignment_method", "geo_uncertain",
        "website", "facebook_url", "instagram_url", "other_socials_json", "google_maps_url", "notes",
    ]
    set_clause = ", ".join(f"{c} = ?" for c in restore_cols) + ", updated_at = ?"
    conn.execute(
        f"UPDATE businesses SET {set_clause} WHERE id = ?;",
        [*[target_before.get(c) for c in restore_cols], now, target_id],
    )

    # Restore moved source records & phones
    if moved_sr_ids:
        placeholders = ",".join("?" for _ in moved_sr_ids)
        conn.execute(
            f"UPDATE source_records SET business_id = ? WHERE id IN ({placeholders});",
            [source_id, *moved_sr_ids],
        )
        conn.execute(
            f"UPDATE business_sources SET business_id = ? WHERE source_record_id IN ({placeholders});",
            [source_id, *moved_sr_ids],
        )
    if moved_phone_ids:
        placeholders = ",".join("?" for _ in moved_phone_ids)
        conn.execute(
            f"UPDATE phone_numbers SET business_id = ? WHERE id IN ({placeholders});",
            [source_id, *moved_phone_ids],
        )

    conn.execute(
        "UPDATE merge_history SET is_reverted = 1, reverted_at = ?, reverted_by = ? WHERE id = ?;",
        (now, actor, merge_id),
    )
    conn.execute(
        """
        INSERT INTO audit_logs (action, entity_type, entity_id, actor, details_json, created_at)
        VALUES ('revert_merge', 'merge_history', ?, ?, ?, ?);
        """,
        (merge_id, actor, json.dumps({"target_id": target_id, "source_id": source_id}), now),
    )
    return {
        "merge_id": merge_id,
        "restored_business_id": source_id,
        "restored_name": source_snap.get("primary_name", ""),
        "target_business_id": target_id,
    }
