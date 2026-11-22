"""Tests for collection engine stop/resume, checkpoints, manual XLSX/GeoJSON import, and PagesJaunes parser."""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path
from typing import Any

import openpyxl

from app.collectors.base import BaseSourceAdapter, CollectedRawRecord, CollectionContext
from app.collectors.manual_import import parse_manual_import_bytes
from app.collectors.pagesjaunes_dz import parse_pagesjaunes_listing_html
from app.database.connection import DatabaseManager
from app.services import collection_engine as ce_mod


class _PauseableFakeAdapter(BaseSourceAdapter):
    """Test-only adapter that simulates multi-wilaya progress with checkpointed stop & resume."""

    key = "osm_overpass"
    name = "Fake Test Adapter"

    def __init__(self, pause_event: threading.Event, stop_after_first: bool = True) -> None:
        self.pause_event = pause_event
        self.stop_after_first = stop_after_first
        self.seen_wilayas: list[int] = []

    def test_connection(self) -> dict[str, Any]:
        return {"ok": True, "message": "ok"}

    def collect(self, ctx: CollectionContext) -> dict[str, Any]:
        done = set(ctx.checkpoint.get("done_wilayas", []))
        discovered = 0
        for w in ctx.selected_wilayas:
            wc = int(w["code"])
            if wc in done:
                continue
            self.seen_wilayas.append(wc)
            rec = CollectedRawRecord(
                source_key="osm_overpass",
                external_id=f"test:w{wc}",
                source_url=f"https://example.org/w/{wc}",
                raw_name=f"Agence Wilaya {wc}",
                raw_phones=["0550112233"],
                raw_wilaya=w["name_fr"],
                raw_lat=36.75 if wc == 16 else 35.7,
                raw_lon=3.05 if wc == 16 else -0.63,
            )
            ctx.on_record(rec, wc)
            ctx.on_wilaya_status(wc, "osm_overpass", "collection_completed", 1, "")
            done.add(wc)
            ctx.checkpoint["done_wilayas"] = sorted(done)
            ctx.save_checkpoint(ctx.checkpoint)
            discovered += 1

            if self.stop_after_first and wc == ctx.selected_wilayas[0]["code"]:
                self.pause_event.set()
                # Wait briefly so caller can issue stop_run()
                deadline = time.time() + 2.0
                while not ctx.is_stop_requested() and time.time() < deadline:
                    time.sleep(0.02)
                if ctx.is_stop_requested():
                    raise InterruptedError("Stopped by test")
        return {"discovered": discovered, "errors": []}


def test_collection_engine_stop_and_resume(temp_db: DatabaseManager, monkeypatch) -> None:
    monkeypatch.setattr(ce_mod, "db_manager", temp_db)

    pause_ev = threading.Event()
    adapter = _PauseableFakeAdapter(pause_ev, stop_after_first=True)
    monkeypatch.setitem(ce_mod.ADAPTER_REGISTRY, "osm_overpass", adapter)

    engine = ce_mod.CollectionEngine()
    run_id = engine.start_run(wilaya_codes=[16, 31], source_keys=["osm_overpass"], search_depth="quick")

    assert pause_ev.wait(timeout=3.0), "Worker did not reach first wilaya checkpoint"
    stop_res = engine.stop_run(run_id)
    assert stop_res["stopped"] is True

    # Wait for worker to exit cleanly as cancelled
    deadline = time.time() + 3.0
    status = ""
    while time.time() < deadline:
        with temp_db.read_connection() as conn:
            row = conn.execute("SELECT status, checkpoint_json, discovered_count FROM collection_runs WHERE id = ?;", (run_id,)).fetchone()
            status = row["status"]
            if status == "cancelled":
                cp = json.loads(row["checkpoint_json"])
                assert cp["done_wilayas"] == [16]
                assert row["discovered_count"] == 1
                break
        time.sleep(0.05)
    assert status == "cancelled"

    # Resume should skip wilaya 16 (already in checkpoint) and finish wilaya 31
    adapter.stop_after_first = False
    adapter.seen_wilayas.clear()
    engine.resume_run(run_id)

    deadline = time.time() + 3.0
    while time.time() < deadline:
        with temp_db.read_connection() as conn:
            row = conn.execute("SELECT status, checkpoint_json, discovered_count FROM collection_runs WHERE id = ?;", (run_id,)).fetchone()
            status = row["status"]
            if status == "completed":
                cp = json.loads(row["checkpoint_json"])
                assert cp["done_wilayas"] == [16, 31]
                assert row["discovered_count"] == 2
                break
        time.sleep(0.05)
    assert status == "completed"
    assert adapter.seen_wilayas == [31]


def test_manual_import_xlsx_and_geojson_and_pagesjaunes_parser() -> None:
    # 1. XLSX import with Arabic & French columns
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["nom", "الاسم_بالعربية", "téléphone", "wilaya", "adresse"])
    ws.append(["Atlas Rent", "اطلس لكراء السيارات", "0550445566 / 021654321", "Bou Saâda", "Rue 1er Novembre"])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_recs = parse_manual_import_bytes(buf.getvalue(), "agencies.xlsx")
    assert len(xlsx_recs) == 1
    assert xlsx_recs[0].raw_name == "Atlas Rent"
    assert xlsx_recs[0].raw_name_ar == "اطلس لكراء السيارات"
    assert len(xlsx_recs[0].raw_phones) == 2

    # 2. GeoJSON FeatureCollection import
    geojson_payload = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [3.05, 36.75]},
                    "properties": {"name": "Geo Auto DZ", "phone": "0770123456", "wilaya": "Alger"},
                }
            ],
        }
    ).encode("utf-8")
    gj_recs = parse_manual_import_bytes(geojson_payload, "export.geojson")
    assert len(gj_recs) == 1
    assert gj_recs[0].raw_lat == 36.75
    assert gj_recs[0].raw_lon == 3.05

    # 3. PagesJaunes DZ HTML listing parser
    pj_html = """
    <div class="company-card">
        <h3>Maghreb Location Auto</h3>
        <div class="address">Rue Larbi Ben M'hidi, Oran</div>
        <a href="tel:+213555998877">Appeler</a>
        <a href="https://maghreb-auto.dz">Site web</a>
    </div>
    """
    pj_recs = parse_pagesjaunes_listing_html(pj_html, "https://www.pagesjaunes-dz.com/Companies/search?q=location")
    assert len(pj_recs) == 1
    assert pj_recs[0].raw_name == "Maghreb Location Auto"
    assert "+213555998877" in pj_recs[0].raw_phones
    assert pj_recs[0].raw_website == "https://maghreb-auto.dz"
