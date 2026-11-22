"""Geographic assignment tests across all 69 wilayas, communes, and edge cases."""

from __future__ import annotations

from app.geography.service import GeographyService


def test_algiers_coordinates_assign_wilaya_16(geo_service: GeographyService) -> None:
    res = geo_service.assign(lat=36.7538, lon=3.0588)
    assert res.in_algeria is True
    assert res.wilaya_code == 16
    assert res.wilaya_name == "Alger"
    assert res.commune_id is not None


def test_new_wilaya_68_bou_saada_assignment(geo_service: GeographyService) -> None:
    # Bou Saada coordinates (~35.2167, 4.1833) must resolve to new wilaya 68, NOT parent 28
    res = geo_service.assign(lat=35.2167, lon=4.1833, raw_wilaya="M'Sila")
    assert res.in_algeria is True
    assert res.wilaya_code == 68
    assert res.wilaya_name == "Bou Saâda"
    assert res.uncertain is False  # Parent-to-child refinement is expected, not conflict


def test_coordinates_outside_algeria_flagged(geo_service: GeographyService) -> None:
    # Paris coordinates
    res = geo_service.assign(lat=48.8566, lon=2.3522, raw_address="Paris, France")
    assert res.in_algeria is False
    assert res.method == "outside_algeria"
    assert res.uncertain is True


def test_missing_coordinates_text_fallback_arabic_and_french(geo_service: GeographyService) -> None:
    res_ar = geo_service.assign(raw_wilaya="تلمسان", raw_commune="مغنية")
    assert res_ar.wilaya_code == 13
    assert res_ar.method == "text_match"

    res_fr = geo_service.assign(raw_wilaya="Aïn Ouessara")
    assert res_fr.wilaya_code == 65


def test_conflicting_wilaya_text_vs_coordinates_flags_uncertain(geo_service: GeographyService) -> None:
    # Coordinates in Oran (31) while text says Constantine (25)
    res = geo_service.assign(lat=35.6971, lon=-0.6308, raw_wilaya="Constantine")
    assert res.wilaya_code == 31
    assert res.uncertain is True
