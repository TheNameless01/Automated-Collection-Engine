"""Excel (.xlsx) and UTF-8 BOM CSV exporters covering all 69 Algerian wilayas."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.core.config import safe_resolve_within, settings

INVALID_SHEET_CHARS_RE = re.compile(r"[\\/*?:\[\]]")

MASTER_HEADERS = [
    "ID",
    "Business Name",
    "Arabic Name",
    "French Name",
    "English Name",
    "Primary Phone",
    "Additional Phones",
    "Full Address",
    "Commune",
    "Wilaya",
    "Wilaya Code",
    "Latitude",
    "Longitude",
    "Website",
    "Facebook",
    "Instagram",
    "Other Social Media",
    "Google Maps URL",
    "Sources",
    "Source URLs",
    "Collection Date",
    "Last Verification Date",
    "Verification Status",
    "Confidence Score",
    "Notes",
]


def _make_sheet_title(code_str: str, name_fr: str) -> str:
    clean = INVALID_SHEET_CHARS_RE.sub("", f"{code_str}-{name_fr}").strip()
    return clean[:31]


def _fetch_export_rows(
    conn: sqlite3.Connection,
    *,
    scope: str = "all",  # all | selected_wilayas | selected_records | verified_only | review_required
    wilaya_codes: list[int] | None = None,
    business_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    where = ["b.is_merged = 0"]
    params: list[Any] = []

    if scope == "verified_only":
        where.append("b.verification_status = 'VERIFIED'")
    elif scope == "review_required":
        where.append("(b.verification_status = 'NEEDS_REVIEW' OR b.geo_uncertain = 1)")
    elif scope == "selected_wilayas" and wilaya_codes:
        ph = ",".join("?" for _ in wilaya_codes)
        where.append(f"b.wilaya_code IN ({ph})")
        params.extend(wilaya_codes)
    elif scope == "selected_records" and business_ids:
        ph = ",".join("?" for _ in business_ids)
        where.append(f"b.id IN ({ph})")
        params.extend(business_ids)

    sql = f"""
        SELECT b.*, w.code_str AS wilaya_code_str
        FROM businesses b
        LEFT JOIN wilayas w ON w.code = b.wilaya_code
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(b.wilaya_code, 999), b.primary_name COLLATE NOCASE;
    """
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    if not rows:
        return []

    biz_ids = [r["id"] for r in rows]
    ph = ",".join("?" for _ in biz_ids)

    # Fetch extra phones
    phones_by_biz: dict[int, list[str]] = {}
    for p in conn.execute(
        f"SELECT business_id, normalized_e164, original_number FROM phone_numbers WHERE business_id IN ({ph}) ORDER BY is_primary DESC, id;",
        biz_ids,
    ).fetchall():
        val = p["normalized_e164"] or p["original_number"]
        if val:
            phones_by_biz.setdefault(int(p["business_id"]), []).append(val)

    # Fetch source provenance
    sources_by_biz: dict[int, list[str]] = {}
    urls_by_biz: dict[int, list[str]] = {}
    for s in conn.execute(
        f"""
        SELECT bs.business_id, src.name AS source_name, bs.source_url
        FROM business_sources bs
        JOIN sources src ON src.id = bs.source_id
        WHERE bs.business_id IN ({ph});
        """,
        biz_ids,
    ).fetchall():
        bid = int(s["business_id"])
        if s["source_name"] not in sources_by_biz.setdefault(bid, []):
            sources_by_biz[bid].append(s["source_name"])
        if s["source_url"] and s["source_url"] not in urls_by_biz.setdefault(bid, []):
            urls_by_biz[bid].append(s["source_url"])

    for r in rows:
        bid = int(r["id"])
        all_p = phones_by_biz.get(bid, [])
        primary = r.get("primary_phone") or (all_p[0] if all_p else "")
        extra = [x for x in all_p if x != primary]
        r["_extra_phones"] = " | ".join(dict.fromkeys(extra))
        r["_sources"] = " | ".join(sources_by_biz.get(bid, []))
        r["_source_urls"] = " | ".join(urls_by_biz.get(bid, []))
        r["_other_socials"] = " | ".join(json.loads(r.get("other_socials_json") or "[]"))

    return rows


def _row_to_master_tuple(r: dict[str, Any]) -> list[Any]:
    return [
        r["id"],
        r["primary_name"],
        r["name_ar"],
        r["name_fr"],
        r["name_en"],
        r["primary_phone"],
        r["_extra_phones"],
        r["full_address"],
        r["commune_name"],
        r["wilaya_name"],
        r.get("wilaya_code_str") or (f"{int(r['wilaya_code']):02d}" if r.get("wilaya_code") else ""),
        r["lat"] if r["lat"] is not None else "",
        r["lon"] if r["lon"] is not None else "",
        r["website"],
        r["facebook_url"],
        r["instagram_url"],
        r["_other_socials"],
        r["google_maps_url"],
        r["_sources"],
        r["_source_urls"],
        r["first_collected_at"],
        r["last_verified_at"] or "",
        r["verification_status"],
        r["confidence_score"],
        r["notes"],
    ]


def _style_header(ws: Any, headers: list[str]) -> None:
    fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.freeze_panes = "A2"


def _auto_fit_columns(ws: Any, max_width: int = 42) -> None:
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 10
        for cell in col[:250]:
            val = str(cell.value or "")
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[col_letter].width = min(max_width, max_len + 3)


def export_csv(
    conn: sqlite3.Connection,
    *,
    exports_dir: Path | None = None,
    scope: str = "all",
    wilaya_codes: list[int] | None = None,
    business_ids: list[int] | None = None,
) -> Path:
    out_dir = (exports_dir or settings.exports_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"dz_car_rentals_{scope}_{ts}.csv"
    out_path = safe_resolve_within(out_dir, filename)

    rows = _fetch_export_rows(conn, scope=scope, wilaya_codes=wilaya_codes, business_ids=business_ids)
    # UTF-8 with BOM for full Arabic/French compatibility in Microsoft Excel
    with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(MASTER_HEADERS)
        for r in rows:
            writer.writerow(_row_to_master_tuple(r))
    return out_path


def export_excel(
    conn: sqlite3.Connection,
    *,
    exports_dir: Path | None = None,
    scope: str = "all",
    wilaya_codes: list[int] | None = None,
    business_ids: list[int] | None = None,
) -> Path:
    out_dir = (exports_dir or settings.exports_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"dz_car_rentals_{scope}_{ts}.xlsx"
    out_path = safe_resolve_within(out_dir, filename)

    rows = _fetch_export_rows(conn, scope=scope, wilaya_codes=wilaya_codes, business_ids=business_ids)
    all_wilayas = [
        dict(r)
        for r in conn.execute("SELECT code, code_str, name_fr, name_ar FROM wilayas ORDER BY code;").fetchall()
    ]

    wb = openpyxl.Workbook()

    # Sheet 1: MASTER
    ws_master = wb.active
    ws_master.title = "MASTER"
    _style_header(ws_master, MASTER_HEADERS)
    for r in rows:
        ws_master.append(_row_to_master_tuple(r))
    _auto_fit_columns(ws_master)

    # Sheet 2: STATISTICS
    ws_stats = wb.create_sheet("STATISTICS")
    _style_header(
        ws_stats,
        [
            "Wilaya Code",
            "Wilaya (French)",
            "Wilaya (Arabic)",
            "Total Agencies",
            "Verified",
            "Unverified",
            "Needs Review",
            "Closed",
            "Missing Phone",
            "Missing Address",
            "Missing GPS",
            "Missing Website",
        ],
    )
    by_wilaya: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("wilaya_code"):
            by_wilaya.setdefault(int(r["wilaya_code"]), []).append(r)

    for w in all_wilayas:
        wc = int(w["code"])
        items = by_wilaya.get(wc, [])
        ws_stats.append(
            [
                w["code_str"],
                w["name_fr"],
                w["name_ar"],
                len(items),
                sum(1 for x in items if x["verification_status"] == "VERIFIED"),
                sum(1 for x in items if x["verification_status"] == "UNVERIFIED"),
                sum(1 for x in items if x["verification_status"] == "NEEDS_REVIEW"),
                sum(1 for x in items if x["verification_status"] == "CLOSED"),
                sum(1 for x in items if not x["primary_phone"]),
                sum(1 for x in items if not x["full_address"]),
                sum(1 for x in items if x["lat"] is None or x["lon"] is None),
                sum(1 for x in items if not x["website"]),
            ]
        )

    # Add source summary block at bottom of STATISTICS
    ws_stats.append([])
    ws_stats.append(["Source Summary", "Records Linked"])
    for sr in conn.execute(
        """
        SELECT s.name, COUNT(DISTINCT bs.business_id) AS biz_cnt
        FROM sources s
        LEFT JOIN business_sources bs ON bs.source_id = s.id
        GROUP BY s.id
        ORDER BY biz_cnt DESC;
        """
    ).fetchall():
        ws_stats.append([sr["name"], sr["biz_cnt"]])
    _auto_fit_columns(ws_stats)

    # Sheet 3: SOURCES
    ws_sources = wb.create_sheet("SOURCES")
    _style_header(
        ws_sources,
        [
            "Business ID",
            "Business Name",
            "Source Name",
            "External ID",
            "Original Source URL",
            "Attribution / License",
            "Raw Phone(s)",
            "Raw Address",
            "Collected At",
        ],
    )
    biz_id_set = {r["id"] for r in rows}
    src_query = conn.execute(
        """
        SELECT sr.business_id, b.primary_name, s.name AS source_name, sr.external_id,
               sr.source_url, sr.attribution_text, sr.raw_phones_json, sr.raw_address, sr.collected_at
        FROM source_records sr
        JOIN sources s ON s.id = sr.source_id
        LEFT JOIN businesses b ON b.id = sr.business_id
        WHERE sr.rejected = 0
        ORDER BY sr.id DESC;
        """
    ).fetchall()
    for sr in src_query:
        if scope != "all" and sr["business_id"] not in biz_id_set:
            continue
        ws_sources.append(
            [
                sr["business_id"] or "",
                sr["primary_name"] or "",
                sr["source_name"],
                sr["external_id"],
                sr["source_url"],
                sr["attribution_text"],
                sr["raw_phones_json"],
                sr["raw_address"],
                sr["collected_at"],
            ]
        )
    _auto_fit_columns(ws_sources)

    # Sheet 4: REVIEW_REQUIRED
    ws_review = wb.create_sheet("REVIEW_REQUIRED")
    _style_header(
        ws_review,
        [
            "Type",
            "ID",
            "Business A / Name",
            "Business B / Wilaya",
            "Score",
            "Status",
            "Notes / Signals",
        ],
    )
    for r in rows:
        if r["verification_status"] == "NEEDS_REVIEW" or r.get("geo_uncertain"):
            ws_review.append(
                [
                    "UNCERTAIN_RECORD",
                    r["id"],
                    r["primary_name"],
                    r["wilaya_name"],
                    r["confidence_score"],
                    r["verification_status"],
                    r["verification_notes"],
                ]
            )
    for dc in conn.execute(
        """
        SELECT dc.*, ba.primary_name AS name_a, bb.primary_name AS name_b
        FROM duplicate_candidates dc
        JOIN businesses ba ON ba.id = dc.business_a_id
        JOIN businesses bb ON bb.id = dc.business_b_id
        WHERE dc.status = 'pending'
        ORDER BY dc.overall_score DESC;
        """
    ).fetchall():
        ws_review.append(
            [
                "SUSPECTED_DUPLICATE",
                dc["id"],
                f"[{dc['business_a_id']}] {dc['name_a']}",
                f"[{dc['business_b_id']}] {dc['name_b']}",
                dc["overall_score"],
                dc["status"],
                dc["signals_json"],
            ]
        )
    _auto_fit_columns(ws_review)

    # Additional 69 Wilaya Sheets (always all 69, including wilayas with zero results)
    for w in all_wilayas:
        wc = int(w["code"])
        sheet_title = _make_sheet_title(w["code_str"], w["name_fr"])
        ws_w = wb.create_sheet(sheet_title)
        _style_header(ws_w, MASTER_HEADERS)
        for r in by_wilaya.get(wc, []):
            ws_w.append(_row_to_master_tuple(r))
        _auto_fit_columns(ws_w)

    wb.save(out_path)
    return out_path
