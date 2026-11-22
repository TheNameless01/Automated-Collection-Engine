"""PagesJaunes Algérie public business directory adapter (respecting robots.txt)."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from app.collectors.base import BaseSourceAdapter, CollectedRawRecord, CollectionContext, ResilientHttpClient

logger = logging.getLogger("dz_finder.collectors.pagesjaunes_dz")

BASE_URL = "https://www.pagesjaunes-dz.com"
SEARCH_TERMS = [
    "location de voiture",
    "location voiture",
    "loueur automobile",
    "كراء السيارات",
]


def parse_pagesjaunes_listing_html(html_text: str, page_url: str) -> list[CollectedRawRecord]:
    soup = BeautifulSoup(html_text, "lxml")
    records: list[CollectedRawRecord] = []

    # PagesJaunes-DZ renders company cards in public search/sector pages (never crawling disallowed /firme/*)
    cards = soup.select(".company-card, .listing-item, .search-result, .card-company, article.company, .result-item")
    if not cards:
        # Fallback: look for structured blocks containing phone links or location headings
        cards = [a.parent for a in soup.select('a[href^="tel:"]') if a.parent]

    for idx, card in enumerate(cards):
        name_el = card.select_one("h2, h3, h4, .company-name, .title, strong")
        name = name_el.get_text(" ", strip=True) if name_el else ""
        if not name or len(name) < 2:
            continue

        text_block = card.get_text(" | ", strip=True)
        phones: list[str] = []
        for tel_link in card.select('a[href^="tel:"]'):
            phones.append(tel_link["href"].replace("tel:", "").strip())
        for m in re.finditer(r"(?:\+213|00213|0)[567234]\d(?:[\s.-]?\d{2}){3,4}", text_block):
            val = m.group(0).strip()
            if val not in phones:
                phones.append(val)

        addr_el = card.select_one(".address, .adresse, .location, [itemprop='streetAddress']")
        raw_addr = addr_el.get_text(" ", strip=True) if addr_el else ""

        href_el = card.select_one("a[href]")
        item_url = urljoin(BASE_URL, href_el["href"]) if href_el else page_url

        website = ""
        for a in card.select("a[href^='http']"):
            h = a["href"]
            if "pagesjaunes-dz.com" not in h and "facebook.com" not in h and "instagram.com" not in h:
                website = h
                break

        records.append(
            CollectedRawRecord(
                source_key="pagesjaunes_dz",
                external_id=f"pagesjaunes_dz:{name[:40]}:{idx}",
                source_url=item_url,
                raw_name=name,
                raw_phones=phones,
                raw_address=raw_addr,
                raw_website=website,
                attribution_text="PagesJaunes Algérie Public Directory",
                raw_payload={"text_snippet": text_block[:400]},
            )
        )
    return records


class PagesJaunesDzAdapter(BaseSourceAdapter):
    key = "pagesjaunes_dz"
    name = "PagesJaunes Algérie Directory"

    def test_connection(self) -> dict[str, Any]:
        client = ResilientHttpClient(rate_limit_seconds=1.5, max_retries=1, timeout_seconds=12.0, respect_robots=True)
        try:
            resp = client.request("GET", f"{BASE_URL}/Companies")
            return {
                "ok": resp.status_code == 200,
                "status_code": resp.status_code,
                "message": f"PagesJaunes DZ reachable (HTTP {resp.status_code}); robots.txt enforced.",
            }
        except Exception as exc:
            return {"ok": False, "message": f"PagesJaunes DZ unavailable: {exc}"}
        finally:
            client.close()

    def collect(self, ctx: CollectionContext) -> dict[str, Any]:
        rate_limit = float(ctx.source_config.get("rate_limit_seconds", 2.5))
        max_retries = int(ctx.source_config.get("max_retries", 2))
        client = ResilientHttpClient(
            rate_limit_seconds=rate_limit,
            max_retries=max_retries,
            timeout_seconds=18.0,
            respect_robots=True,
        )
        discovered = 0
        errors: list[str] = []
        done_queries = set(ctx.checkpoint.get("pagesjaunes_done_queries", []))

        try:
            terms = SEARCH_TERMS[:2] if ctx.search_depth == "quick" else SEARCH_TERMS
            for term in terms:
                if ctx.is_stop_requested():
                    break
                if term in done_queries:
                    continue
                url = f"{BASE_URL}/Companies/search?q={quote_plus(term)}"
                try:
                    resp = client.request("GET", url, stop_fn=ctx.is_stop_requested)
                    if resp.status_code != 200:
                        errors.append(f"{url}: HTTP {resp.status_code}")
                        continue
                    recs = parse_pagesjaunes_listing_html(resp.text, url)
                    for rec in recs:
                        ctx.on_record(rec, None)
                        discovered += 1
                    done_queries.add(term)
                    ctx.checkpoint["pagesjaunes_done_queries"] = sorted(done_queries)
                    ctx.save_checkpoint(ctx.checkpoint)
                except PermissionError as exc:
                    errors.append(f"Robots restriction respected: {exc}")
                except InterruptedError:
                    raise
                except Exception as exc:
                    errors.append(f"{term}: {exc}")
        finally:
            client.close()

        return {"discovered": discovered, "errors": errors}
