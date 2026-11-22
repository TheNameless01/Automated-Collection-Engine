"""OpenStreetMap Overpass API collector with ODbL attribution and 69-wilaya chunking."""

from __future__ import annotations

import logging
from typing import Any

from app.collectors.base import (
    CAR_RENTAL_KEYWORDS_RE,
    BaseSourceAdapter,
    CollectedRawRecord,
    CollectionContext,
    ResilientHttpClient,
)

logger = logging.getLogger("dz_finder.collectors.osm_overpass")

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

ODBL_ATTRIBUTION = "© OpenStreetMap contributors (ODbL) — https://www.openstreetmap.org/copyright"


def parse_osm_element_tags(
    elem_type: str,
    elem_id: int,
    lat: float | None,
    lon: float | None,
    tags: dict[str, str],
    *,
    source_key: str,
    attribution: str,
) -> CollectedRawRecord | None:
    """Convert OSM tags into a CollectedRawRecord if it represents a car rental business."""
    amenity = (tags.get("amenity") or "").lower()
    shop = (tags.get("shop") or "").lower()
    is_explicit_tag = amenity == "car_rental" or shop == "car_rental"

    name = (tags.get("name") or "").strip()
    name_fr = (tags.get("name:fr") or "").strip()
    name_ar = (tags.get("name:ar") or "").strip()
    name_en = (tags.get("name:en") or "").strip()
    desc = " ".join(filter(None, [name, name_fr, name_ar, name_en, tags.get("description", ""), tags.get("note", "")]))

    if not is_explicit_tag:
        # Catch mistagged car rental businesses (office=company, shop=car, tourism=*, etc.)
        if not desc or not CAR_RENTAL_KEYWORDS_RE.search(desc):
            return None

    primary_name = name or name_fr or name_ar or name_en
    if not primary_name:
        primary_name = f"OSM {elem_type}/{elem_id}"

    raw_phones: list[str] = []
    for k in ("phone", "contact:phone", "contact:mobile", "mobile", "telephone"):
        v = (tags.get(k) or "").strip()
        if v:
            raw_phones.append(v)

    addr_parts = [
        tags.get("addr:housenumber", "").strip(),
        tags.get("addr:street", "").strip(),
        tags.get("addr:suburb", "").strip(),
        tags.get("addr:city", "").strip(),
        tags.get("addr:state", "").strip(),
        tags.get("addr:full", "").strip(),
    ]
    full_addr = ", ".join(p for p in addr_parts if p)

    website = (tags.get("website") or tags.get("contact:website") or tags.get("url") or "").strip()
    facebook = (tags.get("contact:facebook") or tags.get("facebook") or "").strip()
    instagram = (tags.get("contact:instagram") or tags.get("instagram") or "").strip()

    return CollectedRawRecord(
        source_key=source_key,
        external_id=f"osm:{elem_type}/{elem_id}",
        source_url=f"https://www.openstreetmap.org/{elem_type}/{elem_id}",
        raw_name=primary_name,
        raw_name_ar=name_ar,
        raw_name_fr=name_fr or (primary_name if not any("\u0600" <= c <= "\u06FF" for c in primary_name) else ""),
        raw_name_en=name_en,
        raw_phones=raw_phones,
        raw_address=full_addr,
        raw_commune=(tags.get("addr:city") or tags.get("addr:suburb") or "").strip(),
        raw_wilaya=(tags.get("addr:state") or tags.get("addr:province") or "").strip(),
        raw_lat=lat,
        raw_lon=lon,
        raw_website=website,
        raw_facebook=facebook,
        raw_instagram=instagram,
        attribution_text=attribution,
        raw_payload={"type": elem_type, "id": elem_id, "tags": tags},
    )


class OsmOverpassAdapter(BaseSourceAdapter):
    key = "osm_overpass"
    name = "OpenStreetMap (Overpass API)"

    def test_connection(self) -> dict[str, Any]:
        client = ResilientHttpClient(rate_limit_seconds=0.5, max_retries=0, timeout_seconds=8.0, respect_robots=False)
        last_err = ""
        try:
            for endpoint in OVERPASS_ENDPOINTS:
                status_url = endpoint.replace("/interpreter", "/status")
                try:
                    resp = client.request("GET", status_url, check_robots=False)
                    if resp.status_code == 200:
                        return {
                            "ok": True,
                            "status_code": 200,
                            "message": f"Overpass API reachable ({status_url}).",
                        }
                    last_err = f"{status_url} returned HTTP {resp.status_code}"
                except Exception as exc:
                    last_err = f"{status_url}: {exc}"
            return {"ok": False, "message": f"Overpass mirrors currently busy or unreachable ({last_err}). Use Local Algeria PBF for offline OSM extraction."}
        finally:
            client.close()

    def _build_bbox_query(self, min_lat: float, min_lon: float, max_lat: float, max_lon: float, depth: str) -> str:
        bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
        if depth == "quick":
            return f"""
[out:json][timeout:45];
(
  nwr["amenity"="car_rental"]({bbox});
  nwr["shop"="car_rental"]({bbox});
);
out center tags;
"""
        return f"""
[out:json][timeout:60];
(
  nwr["amenity"="car_rental"]({bbox});
  nwr["shop"="car_rental"]({bbox});
  nwr["name"~"location.*voiture|rent.*car|car.*rental|كراء.*سيار|تأجير.*سيار",i]({bbox});
  nwr["name:fr"~"location.*voiture|loueur",i]({bbox});
  nwr["name:ar"~"كراء.*سيار|تأجير.*سيار",i]({bbox});
);
out center tags;
"""

    def collect(self, ctx: CollectionContext) -> dict[str, Any]:
        rate_limit = float(ctx.source_config.get("rate_limit_seconds", 2.0))
        max_retries = int(ctx.source_config.get("max_retries", 3))
        client = ResilientHttpClient(
            rate_limit_seconds=rate_limit,
            max_retries=max_retries,
            timeout_seconds=65.0,
            respect_robots=False,
        )
        completed_codes = set(ctx.checkpoint.get("osm_overpass_done_wilayas", []))
        total_discovered = 0
        errors: list[str] = []

        try:
            for w in ctx.selected_wilayas:
                if ctx.is_stop_requested():
                    break
                w_code = int(w["code"])
                if w_code in completed_codes:
                    continue

                ctx.on_wilaya_status(w_code, self.key, "in_progress", 0, "")
                # Small padding around wilaya bbox to catch border agencies cleanly
                min_lat = float(w["min_lat"]) - 0.02
                max_lat = float(w["max_lat"]) + 0.02
                min_lon = float(w["min_lon"]) - 0.02
                max_lon = float(w["max_lon"]) + 0.02
                query = self._build_bbox_query(min_lat, min_lon, max_lat, max_lon, ctx.search_depth)

                data: dict[str, Any] | None = None
                last_err = ""
                for endpoint in OVERPASS_ENDPOINTS:
                    try:
                        resp = client.request(
                            "POST",
                            endpoint,
                            data={"data": query},
                            stop_fn=ctx.is_stop_requested,
                            check_robots=False,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            break
                        last_err = f"HTTP {resp.status_code} from {endpoint}"
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        last_err = f"{endpoint}: {exc}"

                if data is None:
                    errors.append(f"Wilaya {w_code:02d}: {last_err}")
                    ctx.on_wilaya_status(w_code, self.key, "sources_unavailable", 0, last_err)
                    continue

                elements = data.get("elements", [])
                count_w = 0
                for el in elements:
                    if ctx.is_stop_requested():
                        break
                    etype = el.get("type", "node")
                    eid = int(el["id"])
                    lat = el.get("lat") or (el.get("center") or {}).get("lat")
                    lon = el.get("lon") or (el.get("center") or {}).get("lon")
                    tags = el.get("tags") or {}
                    rec = parse_osm_element_tags(
                        etype,
                        eid,
                        float(lat) if lat is not None else None,
                        float(lon) if lon is not None else None,
                        tags,
                        source_key=self.key,
                        attribution=ODBL_ATTRIBUTION,
                    )
                    if rec is not None:
                        ctx.on_record(rec, w_code)
                        count_w += 1
                        total_discovered += 1

                completed_codes.add(w_code)
                ctx.checkpoint["osm_overpass_done_wilayas"] = sorted(completed_codes)
                ctx.save_checkpoint(ctx.checkpoint)
                cov = "collection_completed" if count_w > 0 else "no_results_found"
                ctx.on_wilaya_status(w_code, self.key, cov, count_w, "")
        finally:
            client.close()

        return {"discovered": total_discovered, "errors": errors}
