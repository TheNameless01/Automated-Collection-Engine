"""Local OpenStreetMap Algeria PBF collector using PyOsmium (Geofabrik extract)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import osmium

from app.collectors.base import BaseSourceAdapter, CollectedRawRecord, CollectionContext
from app.collectors.osm_overpass import ODBL_ATTRIBUTION, parse_osm_element_tags
from app.core.config import safe_resolve_within, settings

logger = logging.getLogger("dz_finder.collectors.osm_pbf")


class _CarRentalPbfHandler(osmium.SimpleHandler):
    def __init__(self, on_match: Any, stop_fn: Any) -> None:
        super().__init__()
        self.on_match = on_match
        self.stop_fn = stop_fn
        self.matched_count = 0

    def node(self, n: osmium.osm.Node) -> None:
        if self.stop_fn():
            return
        if not n.tags:
            return
        tags = {t.k: t.v for t in n.tags}
        lat = n.location.lat if n.location.valid() else None
        lon = n.location.lon if n.location.valid() else None
        rec = parse_osm_element_tags(
            "node",
            n.id,
            lat,
            lon,
            tags,
            source_key="osm_pbf",
            attribution=ODBL_ATTRIBUTION,
        )
        if rec is not None:
            self.matched_count += 1
            self.on_match(rec)

    def way(self, w: osmium.osm.Way) -> None:
        if self.stop_fn():
            return
        if not w.tags:
            return
        tags = {t.k: t.v for t in w.tags}
        # Compute centroid from valid way node locations
        lats: list[float] = []
        lons: list[float] = []
        for nd in w.nodes:
            if nd.location.valid():
                lats.append(nd.location.lat)
                lons.append(nd.location.lon)
        lat = sum(lats) / len(lats) if lats else None
        lon = sum(lons) / len(lons) if lons else None
        rec = parse_osm_element_tags(
            "way",
            w.id,
            lat,
            lon,
            tags,
            source_key="osm_pbf",
            attribution=ODBL_ATTRIBUTION,
        )
        if rec is not None:
            self.matched_count += 1
            self.on_match(rec)


def parse_pbf_file(pbf_path: Path, on_match: Any, stop_fn: Any = lambda: False) -> int:
    """Stream-parse an .osm.pbf file locally without loading the full file into memory."""
    if not pbf_path.exists():
        raise FileNotFoundError(f"PBF file not found: {pbf_path}")
    handler = _CarRentalPbfHandler(on_match, stop_fn)
    handler.apply_file(str(pbf_path), locations=True)
    return handler.matched_count


def download_algeria_pbf(
    url: str | None = None,
    dest_path: Path | None = None,
    progress_cb: Any = None,
) -> Path:
    """Download Algeria PBF extract with remote size check to avoid redundant downloads."""
    target_url = url or settings.osm_pbf_url
    dest = dest_path or safe_resolve_within(settings.raw_dir, "algeria-latest.osm.pbf")
    tmp_dest = dest.with_suffix(".osm.pbf.part")

    with httpx.Client(follow_redirects=True, timeout=60.0, headers={"User-Agent": settings.user_agent}) as client:
        head = client.head(target_url)
        remote_size = int(head.headers.get("Content-Length", "0") or "0")
        if dest.exists() and remote_size > 0 and dest.stat().st_size == remote_size:
            return dest

        with client.stream("GET", target_url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", "0") or "0")
            downloaded = 0
            with tmp_dest.open("wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total > 0:
                        progress_cb(downloaded, total)
        tmp_dest.replace(dest)
    return dest


class OsmPbfAdapter(BaseSourceAdapter):
    key = "osm_pbf"
    name = "OpenStreetMap Algeria Extract (Geofabrik PBF)"

    def _get_pbf_path(self, config: dict[str, Any]) -> Path:
        filename = str(config.get("local_pbf_filename") or "algeria-latest.osm.pbf")
        return safe_resolve_within(settings.raw_dir, filename)

    def test_connection(self) -> dict[str, Any]:
        pbf_path = safe_resolve_within(settings.raw_dir, "algeria-latest.osm.pbf")
        if pbf_path.exists():
            size_mb = round(pbf_path.stat().st_size / (1024 * 1024), 1)
            return {"ok": True, "local_ready": True, "message": f"Local PBF ready ({size_mb} MB)."}
        try:
            with httpx.Client(follow_redirects=True, timeout=10.0, headers={"User-Agent": settings.user_agent}) as c:
                r = c.head(settings.osm_pbf_url)
                size_mb = round(int(r.headers.get("Content-Length", "0") or "0") / (1024 * 1024), 1)
                return {
                    "ok": r.status_code == 200,
                    "local_ready": False,
                    "message": f"Remote Geofabrik PBF available ({size_mb} MB); download from Sources or enable auto_download.",
                }
        except Exception as exc:
            return {"ok": False, "local_ready": False, "message": f"No local PBF and remote unreachable: {exc}"}

    def collect(self, ctx: CollectionContext) -> dict[str, Any]:
        if ctx.checkpoint.get("osm_pbf_completed"):
            return {"discovered": 0, "errors": []}

        pbf_path = self._get_pbf_path(ctx.source_config)
        auto_download = bool(ctx.source_config.get("auto_download", False))

        if not pbf_path.exists():
            if not auto_download:
                msg = f"Local PBF not present at {pbf_path.name}; skipping offline PBF scan (download via Sources or enable auto_download)."
                logger.info(msg)
                return {"discovered": 0, "errors": [msg]}
            pbf_path = download_algeria_pbf(settings.osm_pbf_url, pbf_path)

        discovered = 0

        def _handle(rec: CollectedRawRecord) -> None:
            nonlocal discovered
            ctx.on_record(rec, None)
            discovered += 1

        parse_pbf_file(pbf_path, _handle, stop_fn=ctx.is_stop_requested)
        if not ctx.is_stop_requested():
            ctx.checkpoint["osm_pbf_completed"] = True
            ctx.save_checkpoint(ctx.checkpoint)
        return {"discovered": discovered, "errors": []}
