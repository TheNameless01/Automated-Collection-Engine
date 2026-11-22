"""Manual CSV, Excel (.xlsx), and GeoJSON import adapter for user-supplied datasets."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import openpyxl

from app.collectors.base import CollectedRawRecord
from app.processors.phone_processor import split_raw_phone_strings

# Flexible header aliases supporting French, Arabic, and English spreadsheets
COLUMN_ALIASES: dict[str, set[str]] = {
    "name": {"name", "business_name", "primary_name", "nom", "agence", "raison_sociale", "الاسم", "اسم_الوكالة"},
    "name_ar": {"name_ar", "nom_ar", "arabic_name", "الاسم_بالعربية"},
    "name_fr": {"name_fr", "nom_fr", "french_name"},
    "name_en": {"name_en", "english_name"},
    "phone": {"phone", "primary_phone", "telephone", "tel", "téléphone", "mobile", "gsm", "الهاتف"},
    "extra_phones": {"extra_phones", "additional_phones", "phones", "autres_telephones"},
    "address": {"address", "full_address", "adresse", "العنوان"},
    "commune": {"commune", "city", "ville", "البلدية"},
    "wilaya": {"wilaya", "wilaya_name", "province", "state", "الولاية"},
    "lat": {"lat", "latitude", "gps_lat"},
    "lon": {"lon", "lng", "longitude", "gps_lon"},
    "website": {"website", "site", "site_web", "url"},
    "facebook": {"facebook", "facebook_url", "fb"},
    "instagram": {"instagram", "instagram_url", "ig"},
    "google_maps_url": {"google_maps_url", "gmaps", "maps_url", "google_maps"},
    "source_url": {"source_url", "original_url", "lien"},
    "notes": {"notes", "note", "remarques", "ملاحظات"},
}


def _map_headers(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, h in enumerate(headers):
        norm = str(h or "").strip().lower().replace(" ", "_")
        for field_key, aliases in COLUMN_ALIASES.items():
            if norm in aliases and field_key not in mapping:
                mapping[field_key] = idx
    return mapping


def _row_to_record(row_dict: dict[str, Any], idx: int, filename: str) -> CollectedRawRecord | None:
    name = str(row_dict.get("name") or row_dict.get("name_fr") or row_dict.get("name_ar") or "").strip()
    if not name:
        return None

    phones = split_raw_phone_strings(
        [str(row_dict.get("phone") or ""), str(row_dict.get("extra_phones") or "")]
    )
    lat_raw = row_dict.get("lat")
    lon_raw = row_dict.get("lon")
    lat = float(lat_raw) if lat_raw not in (None, "") else None
    lon = float(lon_raw) if lon_raw not in (None, "") else None

    return CollectedRawRecord(
        source_key="manual_import",
        external_id=f"manual:{filename}:{idx}",
        source_url=str(row_dict.get("source_url") or ""),
        raw_name=name,
        raw_name_ar=str(row_dict.get("name_ar") or "").strip(),
        raw_name_fr=str(row_dict.get("name_fr") or "").strip(),
        raw_name_en=str(row_dict.get("name_en") or "").strip(),
        raw_phones=phones,
        raw_address=str(row_dict.get("address") or "").strip(),
        raw_commune=str(row_dict.get("commune") or "").strip(),
        raw_wilaya=str(row_dict.get("wilaya") or "").strip(),
        raw_lat=lat,
        raw_lon=lon,
        raw_website=str(row_dict.get("website") or "").strip(),
        raw_facebook=str(row_dict.get("facebook") or "").strip(),
        raw_instagram=str(row_dict.get("instagram") or "").strip(),
        raw_google_maps_url=str(row_dict.get("google_maps_url") or "").strip(),
        attribution_text=f"Manual Import ({filename})",
        notes=str(row_dict.get("notes") or "").strip(),
        raw_payload=row_dict,
    )


def parse_manual_import_bytes(content: bytes, filename: str) -> list[CollectedRawRecord]:
    ext = Path(filename).suffix.lower()
    records: list[CollectedRawRecord] = []

    if ext == ".csv":
        text = content.decode("utf-8-sig", errors="replace")
        sample = text[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(text), dialect)
        rows = list(reader)
        if not rows:
            return []
        col_map = _map_headers(rows[0])
        for idx, row in enumerate(rows[1:], start=2):
            row_dict = {k: (row[col_i] if col_i < len(row) else "") for k, col_i in col_map.items()}
            rec = _row_to_record(row_dict, idx, filename)
            if rec:
                records.append(rec)

    elif ext in (".xlsx", ".xlsm"):
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(c or "") for c in next(rows_iter, ())]
        col_map = _map_headers(headers)
        for idx, row in enumerate(rows_iter, start=2):
            row_dict = {k: (row[col_i] if col_i < len(row) else "") for k, col_i in col_map.items()}
            rec = _row_to_record(row_dict, idx, filename)
            if rec:
                records.append(rec)
        wb.close()

    elif ext in (".json", ".geojson"):
        data = json.loads(content.decode("utf-8-sig"))
        items = data.get("features", []) if isinstance(data, dict) and data.get("type") == "FeatureCollection" else data
        if isinstance(items, list):
            for idx, item in enumerate(items, start=1):
                if isinstance(item, dict) and item.get("type") == "Feature":
                    props = dict(item.get("properties") or {})
                    coords = (item.get("geometry") or {}).get("coordinates") or []
                    if len(coords) >= 2:
                        props.setdefault("lon", coords[0])
                        props.setdefault("lat", coords[1])
                    item = props
                if isinstance(item, dict):
                    normalized_item = {}
                    for k, v in item.items():
                        low = str(k).strip().lower().replace(" ", "_")
                        for field_key, aliases in COLUMN_ALIASES.items():
                            if low in aliases:
                                normalized_item[field_key] = v
                    rec = _row_to_record(normalized_item, idx, filename)
                    if rec:
                        records.append(rec)
    else:
        raise ValueError(f"Unsupported import format '{ext}'. Use CSV, XLSX, JSON, or GeoJSON.")

    return records
