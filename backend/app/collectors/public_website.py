"""Public business website enrichment collector (robots.txt enforced, no login bypass)."""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from app.collectors.base import BaseSourceAdapter, CollectedRawRecord, CollectionContext, ResilientHttpClient
from app.database.connection import db_manager
from app.processors.text_normalizer import is_valid_http_url

logger = logging.getLogger("dz_finder.collectors.public_website")

_PHONE_PATTERN = re.compile(r"(?:\+213|00213|0)(?:5|6|7|2\d|3\d|4\d)(?:[\s.\-]?\d{2}){3,4}")


def extract_public_website_contacts(html_text: str, site_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html_text, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = soup.get_text(" ", strip=True)

    phones: list[str] = []
    for a in soup.select('a[href^="tel:"]'):
        val = a["href"].replace("tel:", "").strip()
        if val and val not in phones:
            phones.append(val)
    for m in _PHONE_PATTERN.finditer(text):
        val = m.group(0).strip()
        if val not in phones:
            phones.append(val)

    facebook = ""
    instagram = ""
    other_socials: list[str] = []
    for a in soup.select("a[href]"):
        href = a["href"].strip()
        low = href.lower()
        if "facebook.com" in low or "fb.com" in low:
            if not facebook:
                facebook = href
        elif "instagram.com" in low:
            if not instagram:
                instagram = href
        elif any(dom in low for dom in ("linkedin.com", "tiktok.com", "youtube.com")):
            if href not in other_socials:
                other_socials.append(href)

    return {
        "title": title,
        "phones": phones[:6],
        "facebook": facebook,
        "instagram": instagram,
        "other_socials": other_socials[:5],
        "source_url": site_url,
    }


class PublicWebsiteAdapter(BaseSourceAdapter):
    key = "business_website"
    name = "Public Agency Websites (Enrichment)"

    def test_connection(self) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "Public website enrichment adapter ready (enriches discovered agency websites while checking robots.txt).",
        }

    def collect(self, ctx: CollectionContext) -> dict[str, Any]:
        max_sites = int(ctx.source_config.get("max_sites_per_run", 30))
        if ctx.search_depth == "quick":
            max_sites = min(max_sites, 10)
        rate_limit = float(ctx.source_config.get("rate_limit_seconds", 2.0))

        with db_manager.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, primary_name, website, wilaya_code
                FROM businesses
                WHERE is_merged = 0 AND website != ''
                ORDER BY updated_at DESC
                LIMIT ?;
                """,
                (max_sites,),
            ).fetchall()

        done_sites = set(ctx.checkpoint.get("website_done_urls", []))
        client = ResilientHttpClient(
            rate_limit_seconds=rate_limit,
            max_retries=1,
            timeout_seconds=12.0,
            respect_robots=True,
        )
        discovered = 0
        errors: list[str] = []

        try:
            for r in rows:
                if ctx.is_stop_requested():
                    break
                url = r["website"]
                if not is_valid_http_url(url) or url in done_sites:
                    continue
                try:
                    resp = client.request("GET", url, stop_fn=ctx.is_stop_requested)
                    if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                        info = extract_public_website_contacts(resp.text, url)
                        if info["phones"] or info["facebook"] or info["instagram"]:
                            rec = CollectedRawRecord(
                                source_key=self.key,
                                external_id=f"website:{url}",
                                source_url=url,
                                raw_name=r["primary_name"],
                                raw_phones=info["phones"],
                                raw_website=url,
                                raw_facebook=info["facebook"],
                                raw_instagram=info["instagram"],
                                raw_other_socials=info["other_socials"],
                                attribution_text=f"Public Website ({url})",
                                raw_payload={"title": info["title"]},
                            )
                            ctx.on_record(rec, r["wilaya_code"])
                            discovered += 1
                    done_sites.add(url)
                    ctx.checkpoint["website_done_urls"] = sorted(done_sites)
                    ctx.save_checkpoint(ctx.checkpoint)
                except PermissionError:
                    done_sites.add(url)
                except InterruptedError:
                    raise
                except Exception as exc:
                    errors.append(f"{url}: {exc}")
        finally:
            client.close()

        return {"discovered": discovered, "errors": errors}
