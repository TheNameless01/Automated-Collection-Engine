"""Build authoritative 69-wilaya and 1,541-commune geographic dataset for Algeria.

Sources:
- Law No. 84-09 (48 wilayas), Law No. 19-12 (wilayas 49-58), Law No. 26-06 (wilayas 59-69).
- Commune coordinates and administrative hierarchy: ihahachi/Algeria-Cities (1,541 communes).
- National boundary polygon: geoBoundaries DZA ADM0 simplified GeoJSON.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPoint, MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import unary_union, voronoi_diagram

ROOT_DIR = Path(__file__).resolve().parent.parent
BOUNDARIES_DIR = ROOT_DIR / "data" / "boundaries"

CITIES_URL = "https://raw.githubusercontent.com/ihahachi/Algeria-Cities/main/json/algeria_cities.json"
ADM0_META_URL = "https://www.geoboundaries.org/api/current/gbOpen/DZA/ADM0/"

# Authoritative 69 Wilayas registry (Code 01-69) with official French, Arabic, English names,
# parent wilaya (for 49-69), and common alternative spellings / transliterations.
OFFICIAL_WILAYAS: dict[int, dict[str, Any]] = {
    1: {"fr": "Adrar", "ar": "أدرار", "en": "Adrar", "alt": ["Adrar", "أدرار"]},
    2: {"fr": "Chlef", "ar": "الشلف", "en": "Chlef", "alt": ["Chlef", "Ech Cheliff", "El Asnam", "الشلف"]},
    3: {"fr": "Laghouat", "ar": "الأغواط", "en": "Laghouat", "alt": ["Laghouat", "El Aghouat", "الأغواط"]},
    4: {"fr": "Oum El Bouaghi", "ar": "أم البواقي", "en": "Oum El Bouaghi", "alt": ["Oum El Bouaghi", "Oum El-Bouaghi", "OEB", "أم البواقي"]},
    5: {"fr": "Batna", "ar": "باتنة", "en": "Batna", "alt": ["Batna", "باتنة"]},
    6: {"fr": "Béjaïa", "ar": "بجاية", "en": "Bejaia", "alt": ["Béjaïa", "Bejaia", "Bougie", "Bgayet", "بجاية"]},
    7: {"fr": "Biskra", "ar": "بسكرة", "en": "Biskra", "alt": ["Biskra", "بسكرة"]},
    8: {"fr": "Béchar", "ar": "بشار", "en": "Bechar", "alt": ["Béchar", "Bechar", "بشار"]},
    9: {"fr": "Blida", "ar": "البليدة", "en": "Blida", "alt": ["Blida", "El Boulaida", "البليدة"]},
    10: {"fr": "Bouira", "ar": "البويرة", "en": "Bouira", "alt": ["Bouira", "Tubirets", "البويرة"]},
    11: {"fr": "Tamanrasset", "ar": "تمنراست", "en": "Tamanrasset", "alt": ["Tamanrasset", "Tamanghasset", "Tam", "تمنراست"]},
    12: {"fr": "Tébessa", "ar": "تبسة", "en": "Tebessa", "alt": ["Tébessa", "Tebessa", "Tbessa", "تبسة"]},
    13: {"fr": "Tlemcen", "ar": "تلمسان", "en": "Tlemcen", "alt": ["Tlemcen", "تلمسان"]},
    14: {"fr": "Tiaret", "ar": "تيارت", "en": "Tiaret", "alt": ["Tiaret", "Tahert", "تيارت"]},
    15: {"fr": "Tizi Ouzou", "ar": "تيزي وزو", "en": "Tizi Ouzou", "alt": ["Tizi Ouzou", "Tizi-Ouzou", "تيزي وزو"]},
    16: {"fr": "Alger", "ar": "الجزائر", "en": "Algiers", "alt": ["Alger", "Algiers", "El Djazair", "Dzayer", "الجزائر", "الجزائر العاصمة"]},
    17: {"fr": "Djelfa", "ar": "الجلفة", "en": "Djelfa", "alt": ["Djelfa", "الجلفة"]},
    18: {"fr": "Jijel", "ar": "جيجل", "en": "Jijel", "alt": ["Jijel", "Djidjelli", "جيجل"]},
    19: {"fr": "Sétif", "ar": "سطيف", "en": "Setif", "alt": ["Sétif", "Setif", "Stif", "سطيف"]},
    20: {"fr": "Saïda", "ar": "سعيدة", "en": "Saida", "alt": ["Saïda", "Saida", "سعيدة"]},
    21: {"fr": "Skikda", "ar": "سكيكدة", "en": "Skikda", "alt": ["Skikda", "سكيكدة"]},
    22: {"fr": "Sidi Bel Abbès", "ar": "سيدي بلعباس", "en": "Sidi Bel Abbes", "alt": ["Sidi Bel Abbès", "Sidi Bel Abbes", "SBA", "سيدي بلعباس"]},
    23: {"fr": "Annaba", "ar": "عنابة", "en": "Annaba", "alt": ["Annaba", "Bône", "عنابة"]},
    24: {"fr": "Guelma", "ar": "قالمة", "en": "Guelma", "alt": ["Guelma", "قالمة"]},
    25: {"fr": "Constantine", "ar": "قسنطينة", "en": "Constantine", "alt": ["Constantine", "Qacentina", "قسنطينة"]},
    26: {"fr": "Médéa", "ar": "المدية", "en": "Medea", "alt": ["Médéa", "Medea", "المدية"]},
    27: {"fr": "Mostaganem", "ar": "مستغانم", "en": "Mostaganem", "alt": ["Mostaganem", "Mosta", "مستغانم"]},
    28: {"fr": "M'Sila", "ar": "المسيلة", "en": "M'Sila", "alt": ["M'Sila", "Msila", "M Sila", "المسيلة"]},
    29: {"fr": "Mascara", "ar": "معسكر", "en": "Mascara", "alt": ["Mascara", "Mouaskar", "معسكر"]},
    30: {"fr": "Ouargla", "ar": "ورقلة", "en": "Ouargla", "alt": ["Ouargla", "Wargla", "ورقلة"]},
    31: {"fr": "Oran", "ar": "وهران", "en": "Oran", "alt": ["Oran", "Wahran", "Ouahran", "وهران"]},
    32: {"fr": "El Bayadh", "ar": "البيض", "en": "El Bayadh", "alt": ["El Bayadh", "El-Bayadh", "البيض"]},
    33: {"fr": "Illizi", "ar": "إليزي", "en": "Illizi", "alt": ["Illizi", "إليزي", "اليزي"]},
    34: {"fr": "Bordj Bou Arréridj", "ar": "برج بوعريريج", "en": "Bordj Bou Arreridj", "alt": ["Bordj Bou Arréridj", "Bordj Bou Arreridj", "BBA", "برج بوعريريج"]},
    35: {"fr": "Boumerdès", "ar": "بومرداس", "en": "Boumerdes", "alt": ["Boumerdès", "Boumerdes", "بومرداس"]},
    36: {"fr": "El Tarf", "ar": "الطارف", "en": "El Tarf", "alt": ["El Tarf", "El Taref", "الطارف"]},
    37: {"fr": "Tindouf", "ar": "تندوف", "en": "Tindouf", "alt": ["Tindouf", "تندوف"]},
    38: {"fr": "Tissemsilt", "ar": "تيسمسيلت", "en": "Tissemsilt", "alt": ["Tissemsilt", "تيسمسيلت"]},
    39: {"fr": "El Oued", "ar": "الوادي", "en": "El Oued", "alt": ["El Oued", "Oued Souf", "الوادي"]},
    40: {"fr": "Khenchela", "ar": "خنشلة", "en": "Khenchela", "alt": ["Khenchela", "خنشلة"]},
    41: {"fr": "Souk Ahras", "ar": "سوق أهراس", "en": "Souk Ahras", "alt": ["Souk Ahras", "Souk-Ahras", "سوق أهراس", "سوق اهراس"]},
    42: {"fr": "Tipaza", "ar": "تيبازة", "en": "Tipaza", "alt": ["Tipaza", "Tipasa", "تيبازة"]},
    43: {"fr": "Mila", "ar": "ميلة", "en": "Mila", "alt": ["Mila", "ميلة"]},
    44: {"fr": "Aïn Defla", "ar": "عين الدفلى", "en": "Ain Defla", "alt": ["Aïn Defla", "Ain Defla", "Ain-Defla", "عين الدفلى"]},
    45: {"fr": "Naâma", "ar": "النعامة", "en": "Naama", "alt": ["Naâma", "Naama", "النعامة"]},
    46: {"fr": "Aïn Témouchent", "ar": "عين تموشنت", "en": "Ain Temouchent", "alt": ["Aïn Témouchent", "Ain Temouchent", "عين تموشنت"]},
    47: {"fr": "Ghardaïa", "ar": "غرداية", "en": "Ghardaia", "alt": ["Ghardaïa", "Ghardaia", "غرداية"]},
    48: {"fr": "Relizane", "ar": "غليزان", "en": "Relizane", "alt": ["Relizane", "Ighil Izane", "غليزان"]},
    49: {"fr": "Timimoun", "ar": "تيميمون", "en": "Timimoun", "parent": 1, "alt": ["Timimoun", "تيميمون"]},
    50: {"fr": "Bordj Badji Mokhtar", "ar": "برج باجي مختار", "en": "Bordj Badji Mokhtar", "parent": 1, "alt": ["Bordj Badji Mokhtar", "Bordj Baji Mokhtar", "BBM", "برج باجي مختار"]},
    51: {"fr": "Ouled Djellal", "ar": "أولاد جلال", "en": "Ouled Djellal", "parent": 7, "alt": ["Ouled Djellal", "أولاد جلال", "اولاد جلال"]},
    52: {"fr": "Béni Abbès", "ar": "بني عباس", "en": "Beni Abbes", "parent": 8, "alt": ["Béni Abbès", "Beni Abbes", "بني عباس"]},
    53: {"fr": "In Salah", "ar": "عين صالح", "en": "In Salah", "parent": 11, "alt": ["In Salah", "Ain Salah", "Aïn Salah", "عين صالح"]},
    54: {"fr": "In Guezzam", "ar": "عين قزام", "en": "In Guezzam", "parent": 11, "alt": ["In Guezzam", "Ain Guezzam", "Aïn Guezzam", "عين قزام"]},
    55: {"fr": "Touggourt", "ar": "تقرت", "en": "Touggourt", "parent": 30, "alt": ["Touggourt", "توقرت", "تقرت"]},
    56: {"fr": "Djanet", "ar": "جانت", "en": "Djanet", "parent": 33, "alt": ["Djanet", "جانت"]},
    57: {"fr": "El M'Ghair", "ar": "المغير", "en": "El M'Ghair", "parent": 39, "alt": ["El M'Ghair", "El Meghaier", "El M'ghair", "المغير"]},
    58: {"fr": "El Meniaa", "ar": "المنيعة", "en": "El Meniaa", "parent": 47, "alt": ["El Meniaa", "El Menia", "El Golea", "المنيعة"]},
    59: {"fr": "Aflou", "ar": "أفلو", "en": "Aflou", "parent": 3, "alt": ["Aflou", "آفلو", "أفلو"]},
    60: {"fr": "Barika", "ar": "بريكة", "en": "Barika", "parent": 5, "alt": ["Barika", "بريكة"]},
    61: {"fr": "El Kantara", "ar": "القنطرة", "en": "El Kantara", "parent": 7, "alt": ["El Kantara", "القنطرة"]},
    62: {"fr": "Bir El Ater", "ar": "بئر العاتر", "en": "Bir El Ater", "parent": 12, "alt": ["Bir El Ater", "Bir El-Ater", "بئر العاتر"]},
    63: {"fr": "El Aricha", "ar": "العريشة", "en": "El Aricha", "parent": 13, "alt": ["El Aricha", "العريشة"]},
    64: {"fr": "Ksar Chellala", "ar": "قصر الشلالة", "en": "Ksar Chellala", "parent": 14, "alt": ["Ksar Chellala", "قصر الشلالة"]},
    65: {"fr": "Aïn Ouessara", "ar": "عين وسارة", "en": "Ain Ouessara", "parent": 17, "alt": ["Aïn Ouessara", "Ain Oussera", "Ain Ouessara", "عين وسارة"]},
    66: {"fr": "Messaad", "ar": "مسعد", "en": "Messaad", "parent": 17, "alt": ["Messaad", "Messad", "مسعد"]},
    67: {"fr": "Ksar El Boukhari", "ar": "قصر البخاري", "en": "Ksar El Boukhari", "parent": 26, "alt": ["Ksar El Boukhari", "قصر البخاري"]},
    68: {"fr": "Bou Saâda", "ar": "بوسعادة", "en": "Bou Saada", "parent": 28, "alt": ["Bou Saâda", "Bou Saada", "Boussaâda", "Bousaada", "بوسعادة"]},
    69: {"fr": "El Abiodh Sidi Cheikh", "ar": "الأبيض سيدي الشيخ", "en": "El Abiodh Sidi Cheikh", "parent": 32, "alt": ["El Abiodh Sidi Cheikh", "El Abiodh", "الأبيض سيدي الشيخ"]},
}


def fetch_json(url: str, cache_path: Path) -> Any:
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": "DZCarRentalFinder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    cache_path.write_text(raw, encoding="utf-8")
    return json.loads(raw)


def main() -> None:
    BOUNDARIES_DIR.mkdir(parents=True, exist_ok=True)
    cities_cache = BOUNDARIES_DIR / "raw_algeria_cities.json"
    adm0_cache = BOUNDARIES_DIR / "algeria_adm0.geojson"

    cities_raw = fetch_json(CITIES_URL, cities_cache)
    if not adm0_cache.exists():
        meta = fetch_json(ADM0_META_URL, BOUNDARIES_DIR / "raw_adm0_meta.json")
        gj_url = meta.get("simplifiedGeometryGeoJSON") or meta["gjDownloadURL"]
        fetch_json(gj_url, adm0_cache)

    adm0_data = json.loads(adm0_cache.read_text(encoding="utf-8"))
    adm0_geoms = [shape(feat["geometry"]) for feat in adm0_data["features"]]
    algeria_poly = unary_union(adm0_geoms).buffer(0)

    # Parse and normalize all 1,541 communes
    communes: list[dict[str, Any]] = []
    commune_points: list[tuple[int, Point]] = []
    wilaya_commune_coords: dict[int, list[tuple[float, float]]] = {code: [] for code in OFFICIAL_WILAYAS}

    for row in cities_raw:
        w_code = int(row["wilaya_code"])
        lat = float(row["Lat"])
        lon = float(row["Long"])
        if w_code not in OFFICIAL_WILAYAS:
            raise ValueError(f"Unexpected wilaya code {w_code} in cities dataset")
        commune_entry = {
            "id": int(row["id"]),
            "code_commune": str(row.get("code_commune", "")).zfill(4),
            "wilaya_code": w_code,
            "name_fr": row["commune_name_fr"].strip(),
            "name_ar": row["commune_name"].strip(),
            "daira_name_fr": (row.get("daira_name_fr") or "").strip(),
            "daira_name_ar": (row.get("daira_name") or "").strip(),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
        }
        communes.append(commune_entry)
        commune_points.append((w_code, Point(lon, lat)))
        wilaya_commune_coords[w_code].append((lat, lon))

    # Build watertight Voronoi polygons over Algeria ADM0 using all 1,541 commune centroids
    mp = MultiPoint([pt for _, pt in commune_points])
    # Envelope slightly larger than Algeria
    minx, miny, maxx, maxy = algeria_poly.bounds
    envelope = Polygon([
        (minx - 2.0, miny - 2.0),
        (maxx + 2.0, miny - 2.0),
        (maxx + 2.0, maxy + 2.0),
        (minx - 2.0, maxy + 2.0),
    ])
    vor_collection = voronoi_diagram(mp, envelope=envelope)

    # Assign each Voronoi cell to the commune point inside it -> group by wilaya_code
    wilaya_cells: dict[int, list[Any]] = {code: [] for code in OFFICIAL_WILAYAS}
    for cell in vor_collection.geoms:
        clipped = cell.intersection(algeria_poly)
        if clipped.is_empty:
            continue
        # Find which commune point lies inside this cell
        matched_code = None
        for w_code, pt in commune_points:
            if cell.contains(pt) or cell.distance(pt) < 1e-7:
                matched_code = w_code
                break
        if matched_code is not None:
            wilaya_cells[matched_code].append(clipped)

    wilayas_out: list[dict[str, Any]] = []
    geojson_features: list[dict[str, Any]] = []

    for code in sorted(OFFICIAL_WILAYAS.keys()):
        meta = OFFICIAL_WILAYAS[code]
        coords = wilaya_commune_coords[code]
        if not coords:
            raise ValueError(f"Wilaya {code} has zero communes!")
        avg_lat = sum(c[0] for c in coords) / len(coords)
        avg_lon = sum(c[1] for c in coords) / len(coords)

        cells = wilaya_cells.get(code, [])
        if cells:
            poly = unary_union(cells).simplify(0.005, preserve_topology=True)
        else:
            # Fallback buffer around commune points intersected with Algeria
            pts = MultiPoint([Point(lon, lat) for lat, lon in coords])
            poly = pts.convex_hull.buffer(0.15).intersection(algeria_poly)

        b_minx, b_miny, b_maxx, b_maxy = poly.bounds
        geom_json = mapping(poly)

        wilayas_out.append({
            "code": code,
            "code_str": f"{code:02d}",
            "name_fr": meta["fr"],
            "name_ar": meta["ar"],
            "name_en": meta["en"],
            "alt_names": meta["alt"],
            "parent_wilaya_code": meta.get("parent"),
            "center_lat": round(avg_lat, 6),
            "center_lon": round(avg_lon, 6),
            "min_lat": round(b_miny, 6),
            "max_lat": round(b_maxy, 6),
            "min_lon": round(b_minx, 6),
            "max_lon": round(b_maxx, 6),
            "communes_count": len(coords),
            "boundary_geojson": geom_json,
        })
        geojson_features.append({
            "type": "Feature",
            "properties": {
                "code": code,
                "code_str": f"{code:02d}",
                "name_fr": meta["fr"],
                "name_ar": meta["ar"],
                "name_en": meta["en"],
            },
            "geometry": geom_json,
        })

    (BOUNDARIES_DIR / "algeria_69_wilayas.json").write_text(
        json.dumps(wilayas_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (BOUNDARIES_DIR / "algeria_1541_communes.json").write_text(
        json.dumps(communes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (BOUNDARIES_DIR / "algeria_69_wilayas.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": geojson_features}, ensure_ascii=False),
        encoding="utf-8",
    )
    # Remove intermediate raw cache files so data/boundaries stays clean
    for tmp in ["raw_algeria_cities.json", "raw_adm0_meta.json"]:
        p = BOUNDARIES_DIR / tmp
        if p.exists():
            p.unlink()

    print(f"Built {len(wilayas_out)} wilayas and {len(communes)} communes successfully.")


if __name__ == "__main__":
    main()
