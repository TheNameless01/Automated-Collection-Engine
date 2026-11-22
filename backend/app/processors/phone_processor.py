"""Algerian phone number normalization and validation using python-phonenumbers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberType


@dataclass
class ParsedPhone:
    original_number: str
    normalized_e164: str
    national_format: str
    validation_status: str  # valid_format | invalid_format | unknown | verified_reachable
    number_type: str  # mobile | fixed_line | voip | unknown
    carrier_hint: str


_SPLIT_RE = re.compile(r"[/;|,\n]+")


def _detect_dz_carrier(e164: str, num_type: str) -> str:
    if not e164.startswith("+213"):
        return ""
    nsn = e164[4:]
    if num_type == "mobile" and len(nsn) == 9:
        if nsn.startswith("5"):
            return "Ooredoo"
        if nsn.startswith("6"):
            return "Mobilis"
        if nsn.startswith("7"):
            return "Djezzy"
    if num_type == "fixed_line":
        return "Algérie Télécom"
    return ""


def _map_number_type(pt: int) -> str:
    if pt in (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE):
        return "mobile"
    if pt == PhoneNumberType.FIXED_LINE:
        return "fixed_line"
    if pt == PhoneNumberType.VOIP:
        return "voip"
    return "unknown"


def split_raw_phone_strings(raw_values: Iterable[str]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for val in raw_values:
        if not val:
            continue
        for part in _SPLIT_RE.split(str(val)):
            cleaned = part.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                candidates.append(cleaned)
    return candidates


def normalize_algerian_phone(raw: str) -> ParsedPhone:
    """Normalize an Algerian phone string without guessing or fabricating digits."""
    original = (raw or "").strip()
    if not original:
        return ParsedPhone(
            original_number="",
            normalized_e164="",
            national_format="",
            validation_status="unknown",
            number_type="unknown",
            carrier_hint="",
        )

    # Clean common visual separators while keeping leading +
    cleaned = re.sub(r"[\s.\-()]+", "", original)
    # Handle malformed +2130XXXXXXXXX (e.g. "+213.0555014340" seen in directories)
    if cleaned.startswith("+2130") and len(cleaned) >= 13:
        cleaned = "+213" + cleaned[5:]
    elif cleaned.startswith("002130") and len(cleaned) >= 14:
        cleaned = "+213" + cleaned[6:]
    elif cleaned.startswith("00213"):
        cleaned = "+213" + cleaned[5:]
    elif cleaned.startswith("2130") and len(cleaned) >= 13:
        cleaned = "+213" + cleaned[4:]
    elif cleaned.startswith("213") and len(cleaned) >= 11:
        cleaned = "+" + cleaned

    try:
        parsed = phonenumbers.parse(cleaned, "DZ")
    except NumberParseException:
        return ParsedPhone(
            original_number=original,
            normalized_e164="",
            national_format="",
            validation_status="invalid_format",
            number_type="unknown",
            carrier_hint="",
        )

    if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
        return ParsedPhone(
            original_number=original,
            normalized_e164="",
            national_format="",
            validation_status="invalid_format",
            number_type="unknown",
            carrier_hint="",
        )

    # Ensure it is an Algerian number (+213)
    if parsed.country_code != 213:
        return ParsedPhone(
            original_number=original,
            normalized_e164=phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
            national_format=phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
            validation_status="invalid_format",
            number_type="unknown",
            carrier_hint="",
        )

    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    national = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
    num_type = _map_number_type(phonenumbers.number_type(parsed))
    carrier = _detect_dz_carrier(e164, num_type)

    return ParsedPhone(
        original_number=original,
        normalized_e164=e164,
        national_format=national,
        validation_status="valid_format",
        number_type=num_type,
        carrier_hint=carrier,
    )
