"""Multilingual text, Arabic/French normalization, transliteration, and URL processing."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

_AR_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670\u0640]")

_AR_TO_LATIN: dict[str, str] = {
    "ا": "a",
    "أ": "a",
    "إ": "i",
    "آ": "a",
    "ب": "b",
    "ت": "t",
    "ث": "th",
    "ج": "dj",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "dh",
    "ر": "r",
    "ز": "z",
    "س": "s",
    "ش": "ch",
    "ص": "s",
    "ض": "d",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "k",
    "ك": "k",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "ة": "a",
    "و": "ou",
    "ي": "i",
    "ى": "a",
    "ئ": "i",
    "ؤ": "ou",
    "ڨ": "g",
    "ڤ": "v",
    "پ": "p",
    "چ": "tch",
}

_BOILERPLATE_LATIN = {
    "sarl",
    "eurl",
    "spa",
    "snc",
    "ets",
    "agence",
    "location",
    "de",
    "du",
    "des",
    "voiture",
    "voitures",
    "vehicule",
    "vehicules",
    "auto",
    "automobile",
    "automobiles",
    "rent",
    "a",
    "car",
    "cars",
    "hire",
    "loueur",
    "sans",
    "chauffeur",
    "avec",
    "algerie",
    "dz",
}

_BOILERPLATE_AR = {
    "وكالة",
    "كراء",
    "لكراء",
    "للكراء",
    "تأجير",
    "تاجير",
    "لتأجير",
    "لتاجير",
    "السيارات",
    "سيارات",
    "للسيارات",
    "السيارة",
    "سيارة",
    "السياره",
    "سياره",
    "المركبات",
    "مركبات",
    "للمركبات",
    "الجزائر",
    "شركة",
    "مؤسسة",
}


def normalize_arabic(text: str) -> str:
    if not text:
        return ""
    s = _AR_DIACRITICS_RE.sub("", text)
    s = (
        s.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
    )
    s = re.sub(r"[^\u0600-\u06FF0-9\s]", " ", s)
    return " ".join(s.split())


def normalize_latin(text: str) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", text)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def transliterate_ar_to_latin(text: str) -> str:
    if not text:
        return ""
    tokens: list[str] = []
    for raw_tok in text.split():
        # Split common Arabic definite article prefix 'ال' when followed by >= 2 letters
        tok = raw_tok
        prefix = ""
        norm_tok = normalize_arabic(tok)
        if norm_tok.startswith("ال") and len(norm_tok) >= 4:
            prefix = "al "
            tok_chars = norm_tok[2:]
        else:
            tok_chars = tok
        out: list[str] = []
        for ch in tok_chars:
            if ch in _AR_TO_LATIN:
                out.append(_AR_TO_LATIN[ch])
            elif ch.isalnum() or ch.isspace():
                out.append(ch.lower())
            else:
                out.append(" ")
        part = prefix + "".join(out).strip()
        if part.strip():
            tokens.append(part.strip())
    return " ".join(" ".join(tokens).split())


def phonetic_latin_key(text: str) -> str:
    """Normalize Maghrebi Latin/transliterated spelling differences (el/al, ou/u, dj/j, q/k)."""
    s = normalize_latin(text)
    if not s:
        return ""
    words = []
    for w in s.split():
        if w in ("el", "al"):
            words.append("al")
            continue
        w = w.replace("ou", "u").replace("dj", "j").replace("sh", "ch").replace("q", "k").replace("ph", "f")
        # Collapse double consonants
        w = re.sub(r"([a-z])\1+", r"\1", w)
        words.append(w)
    return " ".join(words)


def strip_business_boilerplate(text: str) -> str:
    """Keep distinctive brand tokens for similarity comparison."""
    if not text:
        return ""
    has_ar = any("\u0600" <= c <= "\u06FF" for c in text)
    if has_ar:
        ar_norm = normalize_arabic(text)
        tokens = [t for t in ar_norm.split() if t not in _BOILERPLATE_AR]
        return " ".join(tokens) if tokens else ar_norm
    lat_norm = normalize_latin(text)
    tokens = [t for t in lat_norm.split() if t not in _BOILERPLATE_LATIN]
    return " ".join(tokens) if tokens else lat_norm


def normalize_business_name(name: str) -> str:
    """Produce a canonical comparison key across Latin/Arabic scripts."""
    if not name:
        return ""
    has_ar = any("\u0600" <= c <= "\u06FF" for c in name)
    has_lat = any("a" <= c.lower() <= "z" for c in name)
    if has_ar and not has_lat:
        return normalize_arabic(name)
    if has_ar and has_lat:
        return normalize_latin(name) + " " + normalize_arabic(name)
    return normalize_latin(name)


def normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        if "." in raw and " " not in raw:
            raw = "https://" + raw
        else:
            return ""
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc or "." not in parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path}".rstrip("/")


def is_valid_http_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme.lower() in ("http", "https") and bool(parsed.netloc) and "." in parsed.netloc


def extract_domain(url: str) -> str:
    norm = normalize_url(url)
    if not norm:
        return ""
    host = urlparse(norm).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_social_handle(url: str, platform: str) -> str:
    norm = normalize_url(url)
    if not norm:
        return ""
    parsed = urlparse(norm)
    host = parsed.netloc.lower()
    if platform == "facebook" and ("facebook.com" in host or "fb.com" in host):
        return f"facebook:{parsed.path.strip('/').lower()}"
    if platform == "instagram" and "instagram.com" in host:
        return f"instagram:{parsed.path.strip('/').lower()}"
    return f"{host}{parsed.path.rstrip('/').lower()}"


def extract_branch_markers(text: str) -> set[str]:
    """Detect explicit branch/annex tokens so different branches are not merged."""
    norm = normalize_latin(text)
    markers = set()
    for m in re.finditer(r"\b(annexe|succursale|agence|filiale|bureau|branch|aeroport|airport)\s*([a-z0-9]+)?", norm):
        markers.add(m.group(0).strip())
    return markers
