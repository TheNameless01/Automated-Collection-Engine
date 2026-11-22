"""Geographic processing for Algeria's 69 wilayas and 1,541 communes.

Assigns businesses to wilayas and communes using:
1. Shapely polygon containment against Algeria ADM0 & 69-wilaya boundaries.
2. Spatial proximity to the 1,541 official commune centroids.
3. Multilingual text matching fallback (French, Arabic, English, transliterations).
Flags uncertain boundary edge cases or coordinate/text conflicts for manual review.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from app.core.config import settings


def normalize_geo_text(text: str) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", text)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    # Normalize common Arabic letter variants
    s = (
        s.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ة", "ه")
        .replace("ى", "ي")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
    )
    s = re.sub(r"[\u064B-\u065F\u0670]", "", s)  # strip Arabic diacritics
    s = s.lower()
    s = re.sub(r"[^a-z0-9\u0600-\u06FF\s]", " ", s)
    s = re.sub(r"\b(wilaya|de|d|el|al|la|le|les|commune|daira)\b", " ", s)
    return " ".join(s.split())


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class GeoAssignmentResult:
    in_algeria: bool
    wilaya_code: int | None
    wilaya_name: str
    commune_id: int | None
    commune_name: str
    method: str
    distance_to_commune_km: float | None
    uncertain: bool
    notes: str


class GeographyService:
    """In-memory spatial + administrative resolver loaded from data/boundaries."""

    def __init__(self, boundaries_dir: Path | None = None) -> None:
        self.boundaries_dir = (boundaries_dir or settings.boundaries_dir).resolve()
        self.wilayas: dict[int, dict[str, Any]] = {}
        self.wilaya_geoms: dict[int, BaseGeometry] = {}
        self.communes: list[dict[str, Any]] = []
        self.communes_by_wilaya: dict[int, list[dict[str, Any]]] = {}
        self.commune_by_id: dict[int, dict[str, Any]] = {}
        self.algeria_geom: BaseGeometry | None = None
        self._wilaya_lookup_terms: list[tuple[str, int]] = []
        self._load()

    def _load(self) -> None:
        adm0_path = self.boundaries_dir / "algeria_adm0.geojson"
        wilayas_path = self.boundaries_dir / "algeria_69_wilayas.json"
        communes_path = self.boundaries_dir / "algeria_1541_communes.json"

        if adm0_path.exists():
            adm0 = json.loads(adm0_path.read_text(encoding="utf-8"))
            from shapely.ops import unary_union

            self.algeria_geom = unary_union([shape(f["geometry"]) for f in adm0["features"]]).buffer(0)

        if wilayas_path.exists():
            w_list = json.loads(wilayas_path.read_text(encoding="utf-8"))
            for w in w_list:
                code = int(w["code"])
                self.wilayas[code] = w
                self.wilaya_geoms[code] = shape(w["boundary_geojson"])
                self.communes_by_wilaya[code] = []
                terms = {w["name_fr"], w["name_ar"], w["name_en"], *w.get("alt_names", [])}
                for t in terms:
                    norm = normalize_geo_text(t)
                    if norm:
                        self._wilaya_lookup_terms.append((norm, code))

        if communes_path.exists():
            self.communes = json.loads(communes_path.read_text(encoding="utf-8"))
            for c in self.communes:
                cid = int(c["id"])
                wcode = int(c["wilaya_code"])
                c["_norm_fr"] = normalize_geo_text(c["name_fr"])
                c["_norm_ar"] = normalize_geo_text(c["name_ar"])
                self.commune_by_id[cid] = c
                self.communes_by_wilaya.setdefault(wcode, []).append(c)

    def is_in_algeria(self, lat: float, lon: float) -> bool:
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return False
        # Fast bounding box prefilter for Algeria (approx lat 18.9..37.2, lon -8.7..12.0)
        if not (18.5 <= lat <= 37.5 and -9.0 <= lon <= 12.5):
            return False
        if self.algeria_geom is not None:
            pt = Point(lon, lat)
            # Small 0.02 deg (~2km) coastal tolerance for port/seafront agencies
            return bool(self.algeria_geom.contains(pt) or self.algeria_geom.distance(pt) <= 0.02)
        return True

    def match_wilaya_text(self, text: str) -> int | None:
        if not text:
            return None
        # Check explicit 2-digit postal/wilaya code at start or after "wilaya"
        m = re.search(r"\b([0-6]?\d)\b", text)
        norm = normalize_geo_text(text)
        if norm:
            # Exact / substring match first (prefer longer names)
            for term, code in sorted(self._wilaya_lookup_terms, key=lambda x: len(x[0]), reverse=True):
                if len(term) >= 3 and (norm == term or f" {term} " in f" {norm} "):
                    return code
            # Fuzzy fallback
            best_score = 0.0
            best_code: int | None = None
            for term, code in self._wilaya_lookup_terms:
                if len(term) < 4:
                    continue
                score = fuzz.ratio(norm, term)
                if score > best_score:
                    best_score = score
                    best_code = code
            if best_score >= 86.0:
                return best_code

        if m:
            num = int(m.group(1))
            if 1 <= num <= 69 and ("wilaya" in text.lower() or text.strip().isdigit()):
                return num
        return None

    def match_commune_text(self, text: str, wilaya_code: int | None = None) -> dict[str, Any] | None:
        norm = normalize_geo_text(text)
        if not norm or len(norm) < 2:
            return None
        pool = self.communes_by_wilaya.get(wilaya_code, []) if wilaya_code else self.communes
        for c in pool:
            if norm == c["_norm_fr"] or norm == c["_norm_ar"]:
                return c
        best_score = 0.0
        best_c: dict[str, Any] | None = None
        for c in pool:
            for cand in (c["_norm_fr"], c["_norm_ar"]):
                if not cand:
                    continue
                score = fuzz.ratio(norm, cand)
                if score > best_score:
                    best_score = score
                    best_c = c
        if best_score >= 87.0:
            return best_c
        return None

    def nearest_commune(
        self, lat: float, lon: float, wilaya_code: int | None = None
    ) -> tuple[dict[str, Any] | None, float]:
        pool = self.communes_by_wilaya.get(wilaya_code, []) if wilaya_code else self.communes
        if not pool:
            pool = self.communes
        best_c: dict[str, Any] | None = None
        best_dist = float("inf")
        for c in pool:
            d = haversine_km(lat, lon, float(c["lat"]), float(c["lon"]))
            if d < best_dist:
                best_dist = d
                best_c = c
        return best_c, best_dist

    def assign(
        self,
        *,
        lat: float | None = None,
        lon: float | None = None,
        raw_wilaya: str = "",
        raw_commune: str = "",
        raw_address: str = "",
    ) -> GeoAssignmentResult:
        """Assign wilaya and commune combining spatial boundaries and text evidence."""
        text_wilaya = self.match_wilaya_text(raw_wilaya) or self.match_wilaya_text(raw_address)

        if lat is not None and lon is not None:
            in_dz = self.is_in_algeria(lat, lon)
            if not in_dz:
                return GeoAssignmentResult(
                    in_algeria=False,
                    wilaya_code=text_wilaya,
                    wilaya_name=self.wilayas[text_wilaya]["name_fr"] if text_wilaya else "",
                    commune_id=None,
                    commune_name=raw_commune.strip(),
                    method="outside_algeria",
                    distance_to_commune_km=None,
                    uncertain=True,
                    notes=f"Coordinates ({lat:.5f}, {lon:.5f}) fall outside Algeria boundary.",
                )

            pt = Point(lon, lat)
            poly_wilaya: int | None = None
            min_boundary_dist = float("inf")
            for wcode, geom in self.wilaya_geoms.items():
                if geom.contains(pt):
                    poly_wilaya = wcode
                    # Measure distance to exterior boundary in degrees (~111km/deg)
                    boundary_dist_km = geom.exterior.distance(pt) * 111.0 if hasattr(geom, "exterior") else geom.boundary.distance(pt) * 111.0
                    min_boundary_dist = boundary_dist_km
                    break

            if poly_wilaya is None:
                # Coastal edge fallback: nearest wilaya polygon within 5km
                best_w = None
                best_d = float("inf")
                for wcode, geom in self.wilaya_geoms.items():
                    d = geom.distance(pt) * 111.0
                    if d < best_d:
                        best_d = d
                        best_w = wcode
                if best_w is not None and best_d <= 5.0:
                    poly_wilaya = best_w
                    min_boundary_dist = best_d

            nearest_c, dist_km = self.nearest_commune(lat, lon, poly_wilaya)
            if poly_wilaya is None and nearest_c is not None:
                poly_wilaya = int(nearest_c["wilaya_code"])
                method = "commune_proximity"
            else:
                method = "boundary_polygon"

            # Check text vs polygon agreement & border proximity
            uncertain = False
            notes_parts: list[str] = []
            if text_wilaya and poly_wilaya and text_wilaya != poly_wilaya:
                # Check if text_wilaya is a parent or child wilaya (e.g. legacy 48-wilaya address vs 69-wilaya polygon)
                parent_of_poly = self.wilayas.get(poly_wilaya, {}).get("parent_wilaya_code")
                if parent_of_poly == text_wilaya:
                    notes_parts.append(
                        f"Legacy parent wilaya ({text_wilaya:02d}) refined to wilaya {poly_wilaya:02d} via coordinates."
                    )
                else:
                    uncertain = True
                    notes_parts.append(
                        f"Coordinate wilaya ({poly_wilaya:02d}) conflicts with text wilaya ({text_wilaya:02d})."
                    )

            if min_boundary_dist < 1.5:
                uncertain = True
                notes_parts.append(f"Point is within {min_boundary_dist:.2f} km of a wilaya boundary.")
            if dist_km > 45.0:
                uncertain = True
                notes_parts.append(f"Nearest commune centroid is {dist_km:.1f} km away.")

            w_name = self.wilayas[poly_wilaya]["name_fr"] if poly_wilaya else ""
            # Prefer text commune if it belongs to assigned wilaya and is consistent
            matched_text_c = self.match_commune_text(raw_commune, poly_wilaya) if raw_commune else None
            chosen_c = matched_text_c or nearest_c

            return GeoAssignmentResult(
                in_algeria=True,
                wilaya_code=poly_wilaya,
                wilaya_name=w_name,
                commune_id=int(chosen_c["id"]) if chosen_c else None,
                commune_name=chosen_c["name_fr"] if chosen_c else raw_commune.strip(),
                method=method,
                distance_to_commune_km=round(dist_km, 2) if dist_km != float("inf") else None,
                uncertain=uncertain,
                notes=" ".join(notes_parts),
            )

        # No coordinates available -> text matching only (flag uncertain if commune/wilaya unresolved)
        matched_c = self.match_commune_text(raw_commune, text_wilaya)
        if matched_c and not text_wilaya:
            text_wilaya = int(matched_c["wilaya_code"])

        if text_wilaya:
            w_name = self.wilayas[text_wilaya]["name_fr"]
            return GeoAssignmentResult(
                in_algeria=True,
                wilaya_code=text_wilaya,
                wilaya_name=w_name,
                commune_id=int(matched_c["id"]) if matched_c else None,
                commune_name=matched_c["name_fr"] if matched_c else raw_commune.strip(),
                method="text_match",
                distance_to_commune_km=None,
                uncertain=(matched_c is None and bool(raw_commune.strip())),
                notes="Assigned from text without GPS coordinates."
                + (" Commune name did not match official list." if (raw_commune.strip() and not matched_c) else ""),
            )

        return GeoAssignmentResult(
            in_algeria=True,
            wilaya_code=None,
            wilaya_name="",
            commune_id=None,
            commune_name=raw_commune.strip(),
            method="unresolved",
            distance_to_commune_km=None,
            uncertain=True,
            notes="Neither coordinates nor recognizable wilaya/commune text provided.",
        )

    def commune_belongs_to_wilaya(self, commune_id: int | None, wilaya_code: int | None) -> bool | None:
        if commune_id is None or wilaya_code is None:
            return None
        c = self.commune_by_id.get(commune_id)
        if not c:
            return False
        return int(c["wilaya_code"]) == int(wilaya_code)


_geo_instance: GeographyService | None = None


def get_geography_service() -> GeographyService:
    global _geo_instance
    if _geo_instance is None:
        _geo_instance = GeographyService()
    return _geo_instance
