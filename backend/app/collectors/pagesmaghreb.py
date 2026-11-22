"""PagesMaghreb public Algerian business directory collector (robots.txt Allow: /)."""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from app.collectors.base import BaseSourceAdapter, CollectedRawRecord, CollectionContext, ResilientHttpClient

logger = logging.getLogger("dz_finder.collectors.pagesmaghreb")

PAGESMAGHREB_CATEGORIES = [
    "https://www.pagesmaghreb.com/entreprises/services-aux-entreprises/automobiles-location-d/algerie",
    "https://www.pagesmaghreb.com/entreprises/vehicules-et-materiels-de-transport/location-d-automobiles-tourisme-et-utilitaires/algerie",
    "https://www.pagesmaghreb.com/entreprises/vehicules-et-materiels-de-transport/voitures-location/algerie",
    "https://www.pagesmaghreb.com/entreprises/services-aux-entreprises/location-d-automobiles-avec-ou-sans-chauffeur/algerie",
]

_FIRM_JSON_RE = re.compile(r'JSON\.parse\(\'(.*?)\'\)', re.DOTALL)


_JS_ESCAPE_RE = re.compile(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|['\"\\/bfnrt])")


def _decode_js_single_quoted_json(raw_js: str) -> str:
    """Decode JS single-quoted string escapes (like \\u0022, \\', \\/) while preserving UTF-8."""

    def _repl(match: re.Match[str]) -> str:
        esc = match.group(1)
        if esc == "\\":
            return "\\"
        if esc == "'":
            return "'"
        if esc == '"':
            return '"'
        if esc == "/":
            return "/"
        if esc in ("b", "f", "n", "r", "t"):
            return "\\" + esc
        if esc.startswith(("u", "x")):
            return chr(int(esc[1:], 16))
        return match.group(0)

    return _JS_ESCAPE_RE.sub(_repl, raw_js)


def parse_pagesmaghreb_html(page_html: str, page_url: str) -> tuple[list[CollectedRawRecord], bool]:
    """Extract structured firm-card entries from a PagesMaghreb category page."""
    soup = BeautifulSoup(page_html, "lxml")
    records: list[CollectedRawRecord] = []

    for card in soup.find_all("firm-card"):
        firm_attr = card.get(":firm") or ""
        link = card.get("link") or page_url
        m = _FIRM_JSON_RE.search(firm_attr)
        if not m:
            continue
        raw_js = html.unescape(m.group(1))
        decoded = _decode_js_single_quoted_json(raw_js)
        try:
            firm = json.loads(decoded, strict=False)
        except json.JSONDecodeError:
            try:
                firm = json.loads(raw_js.replace("\\/", "/"), strict=False)
            except json.JSONDecodeError:
                continue

        firm_id = firm.get("id")
        corp_name = (firm.get("corporate_name") or "").strip()
        usual_name = (firm.get("usual_corporate_name") or "").strip()
        primary_name = usual_name or corp_name
        if not primary_name:
            continue

        addresses = firm.get("addresses") or []
        first_addr = addresses[0] if addresses else {}
        city = first_addr.get("city") or {}
        region = city.get("region") or {}
        raw_wilaya = (region.get("name") or region.get("code") or "").strip()
        raw_commune = (city.get("name") or "").strip()
        raw_address = (first_addr.get("name") or "").strip()

        raw_phones: list[str] = []
        raw_website = ""
        raw_facebook = ""
        raw_instagram = ""
        other_socials: list[str] = []

        for contact in firm.get("contacts") or []:
            if not contact.get("publish", True):
                continue
            for method in contact.get("contactmethods") or []:
                mtype = (method.get("method_type") or "").lower()
                val = (method.get("value") or "").strip()
                if not val:
                    continue
                if any(k in mtype for k in ("téléphone", "telephone", "mobile", "phone", "tel")):
                    raw_phones.append(val)
                elif "site web" in mtype or "website" in mtype:
                    if not raw_website:
                        raw_website = val
                elif "facebook" in mtype:
                    raw_facebook = val
                elif "instagram" in mtype:
                    raw_instagram = val
                elif "linkedin" in mtype or "twitter" in mtype or "youtube" in mtype:
                    other_socials.append(val)

        notes = (firm.get("description") or "").strip()
        if corp_name and usual_name and corp_name != usual_name:
            notes = f"{notes}\nCorporate name: {corp_name}".strip()

        records.append(
            CollectedRawRecord(
                source_key="pagesmaghreb",
                external_id=f"pagesmaghreb:{firm_id or primary_name}",
                source_url=str(link),
                raw_name=primary_name,
                raw_name_fr=primary_name,
                raw_phones=raw_phones,
                raw_address=raw_address,
                raw_commune=raw_commune,
                raw_wilaya=raw_wilaya,
                raw_website=raw_website,
                raw_facebook=raw_facebook,
                raw_instagram=raw_instagram,
                raw_other_socials=other_socials,
                attribution_text="PagesMaghreb Public Business Directory (https://www.pagesmaghreb.com)",
                notes=notes,
                raw_payload=firm,
            )
        )

    # Check if next page link exists
    has_next = bool(soup.select_one('a[rel="next"], li.page-item a[aria-label*="Next"], a[href*="page="]'))
    return records, has_next


class PagesMaghrebAdapter(BaseSourceAdapter):
    key = "pagesmaghreb"
    name = "PagesMaghreb Algeria Directory"

    def test_connection(self) -> dict[str, Any]:
        client = ResilientHttpClient(rate_limit_seconds=1.0, max_retries=1, timeout_seconds=12.0, respect_robots=True)
        try:
            resp = client.request("GET", PAGESMAGHREB_CATEGORIES[0])
            recs, _ = parse_pagesmaghreb_html(resp.text, PAGESMAGHREB_CATEGORIES[0])
            return {
                "ok": resp.status_code == 200,
                "sample_count": len(recs),
                "message": f"PagesMaghreb reachable (HTTP {resp.status_code}, {len(recs)} entries on page 1).",
            }
        except Exception as exc:
            return {"ok": False, "message": f"PagesMaghreb unavailable: {exc}"}
        finally:
            client.close()

    def collect(self, ctx: CollectionContext) -> dict[str, Any]:
        rate_limit = float(ctx.source_config.get("rate_limit_seconds", 2.0))
        max_retries = int(ctx.source_config.get("max_retries", 3))
        max_pages = int(ctx.source_config.get("max_pages_per_category", 10))
        if ctx.search_depth == "quick":
            max_pages = min(max_pages, 2)
        elif ctx.search_depth == "deep":
            max_pages = max(max_pages, 25)

        client = ResilientHttpClient(
            rate_limit_seconds=rate_limit,
            max_retries=max_retries,
            timeout_seconds=20.0,
            respect_robots=True,
        )
        done_urls = set(ctx.checkpoint.get("pagesmaghreb_done_urls", []))
        discovered = 0
        errors: list[str] = []
        seen_ids: set[str] = set()

        try:
            for base_cat in PAGESMAGHREB_CATEGORIES:
                if ctx.is_stop_requested():
                    break
                for page_num in range(1, max_pages + 1):
                    if ctx.is_stop_requested():
                        break
                    page_url = base_cat if page_num == 1 else f"{base_cat}?page={page_num}"
                    if page_url in done_urls:
                        continue
                    try:
                        resp = client.request("GET", page_url, stop_fn=ctx.is_stop_requested)
                        if resp.status_code != 200:
                            errors.append(f"{page_url}: HTTP {resp.status_code}")
                            break
                        recs, has_next = parse_pagesmaghreb_html(resp.text, page_url)
                        if not recs:
                            done_urls.add(page_url)
                            ctx.checkpoint["pagesmaghreb_done_urls"] = sorted(done_urls)
                            ctx.save_checkpoint(ctx.checkpoint)
                            break
                        for rec in recs:
                            if rec.external_id in seen_ids:
                                continue
                            seen_ids.add(rec.external_id)
                            ctx.on_record(rec, None)
                            discovered += 1
                        done_urls.add(page_url)
                        ctx.checkpoint["pagesmaghreb_done_urls"] = sorted(done_urls)
                        ctx.save_checkpoint(ctx.checkpoint)
                        if not has_next:
                            break
                    except InterruptedError:
                        raise
                    except PermissionError as exc:
                        errors.append(str(exc))
                        break
                    except Exception as exc:
                        errors.append(f"{page_url}: {exc}")
                        break
        finally:
            client.close()

        return {"discovered": discovered, "errors": errors}
