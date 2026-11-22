"""Background collection engine with progress tracking, safe stop, and resume."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from app.collectors.base import BaseSourceAdapter, CollectedRawRecord, CollectionContext
from app.collectors.osm_overpass import OsmOverpassAdapter
from app.collectors.osm_pbf import OsmPbfAdapter
from app.collectors.pagesjaunes_dz import PagesJaunesDzAdapter
from app.collectors.pagesmaghreb import PagesMaghrebAdapter
from app.collectors.public_website import PublicWebsiteAdapter
from app.core.logging_config import log_with_context
from app.database.connection import db_manager
from app.geography.service import get_geography_service
from app.services.ingestion_service import ingest_raw_record

logger = logging.getLogger("dz_finder.collection_engine")

ADAPTER_REGISTRY: dict[str, BaseSourceAdapter] = {
    "osm_overpass": OsmOverpassAdapter(),
    "osm_pbf": OsmPbfAdapter(),
    "pagesmaghreb": PagesMaghrebAdapter(),
    "pagesjaunes_dz": PagesJaunesDzAdapter(),
    "business_website": PublicWebsiteAdapter(),
}


class CollectionEngine:
    """Manages non-blocking background collection runs with checkpointed resume."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_thread: threading.Thread | None = None
        self._active_run_id: int | None = None
        self._stop_event = threading.Event()

    def is_running(self) -> bool:
        with self._lock:
            return self._active_thread is not None and self._active_thread.is_alive()

    def get_active_run_id(self) -> int | None:
        with self._lock:
            if self._active_thread is not None and self._active_thread.is_alive():
                return self._active_run_id
            return None

    def start_run(
        self,
        *,
        wilaya_codes: list[int] | None = None,
        commune_ids: list[int] | None = None,
        source_keys: list[str] | None = None,
        search_depth: str = "standard",
        notes: str = "",
    ) -> int:
        if self.is_running():
            raise RuntimeError("A collection run is already active.")

        with db_manager.transaction() as conn:
            if wilaya_codes:
                ph = ",".join("?" for _ in wilaya_codes)
                w_rows = conn.execute(
                    f"SELECT code, code_str, name_fr, name_ar, min_lat, max_lat, min_lon, max_lon FROM wilayas WHERE code IN ({ph}) ORDER BY code;",
                    wilaya_codes,
                ).fetchall()
            else:
                w_rows = conn.execute(
                    "SELECT code, code_str, name_fr, name_ar, min_lat, max_lat, min_lon, max_lon FROM wilayas ORDER BY code;"
                ).fetchall()

            if source_keys:
                ph = ",".join("?" for _ in source_keys)
                s_rows = conn.execute(
                    f"SELECT * FROM sources WHERE key IN ({ph}) AND enabled = 1;",
                    source_keys,
                ).fetchall()
            else:
                s_rows = conn.execute(
                    "SELECT * FROM sources WHERE enabled = 1 AND source_type != 'manual_import';"
                ).fetchall()

            valid_sources = [dict(r) for r in s_rows if r["key"] in ADAPTER_REGISTRY]
            if not valid_sources:
                raise ValueError("No enabled automated sources selected.")

            selected_w_codes = [int(r["code"]) for r in w_rows]
            selected_s_keys = [s["key"] for s in valid_sources]
            now = datetime.now(timezone.utc).isoformat()

            cur = conn.execute(
                """
                INSERT INTO collection_runs (
                    status, started_at, stop_requested, search_depth,
                    selected_wilayas_json, selected_communes_json, selected_sources_json,
                    total_tasks, completed_tasks, notes
                ) VALUES ('running', ?, 0, ?, ?, ?, ?, ?, 0, ?);
                """,
                (
                    now,
                    search_depth,
                    json.dumps(selected_w_codes),
                    json.dumps(commune_ids or []),
                    json.dumps(selected_s_keys),
                    len(selected_w_codes) * len(selected_s_keys),
                    notes,
                ),
            )
            run_id = int(cur.lastrowid)

            for w_code in selected_w_codes:
                for sk in selected_s_keys:
                    conn.execute(
                        """
                        INSERT INTO collection_wilaya_progress (
                            run_id, wilaya_code, source_key, coverage_status, updated_at
                        ) VALUES (?, ?, ?, 'not_started', ?);
                        """,
                        (run_id, w_code, sk, now),
                    )

        self._launch_worker(run_id)
        return run_id

    def resume_run(self, run_id: int) -> int:
        if self.is_running():
            raise RuntimeError("A collection run is already active.")
        with db_manager.transaction() as conn:
            row = conn.execute("SELECT * FROM collection_runs WHERE id = ?;", (run_id,)).fetchone()
            if not row:
                raise ValueError(f"Collection run {run_id} not found.")
            if row["status"] == "completed":
                raise ValueError(f"Collection run {run_id} is already completed.")
            conn.execute(
                "UPDATE collection_runs SET status = 'running', stop_requested = 0, finished_at = NULL WHERE id = ?;",
                (run_id,),
            )
        self._launch_worker(run_id)
        return run_id

    def stop_run(self, run_id: int | None = None) -> dict[str, Any]:
        target_id = run_id or self.get_active_run_id()
        if not target_id:
            return {"stopped": False, "message": "No active collection run."}
        self._stop_event.set()
        with db_manager.transaction() as conn:
            conn.execute("UPDATE collection_runs SET stop_requested = 1 WHERE id = ?;", (target_id,))
        log_with_context(logger, logging.INFO, f"Stop requested for collection run {target_id}", run_id=target_id)
        return {"stopped": True, "run_id": target_id}

    def _launch_worker(self, run_id: int) -> None:
        self._stop_event.clear()
        with self._lock:
            self._active_run_id = run_id
            t = threading.Thread(target=self._run_worker, args=(run_id,), daemon=True, name=f"collector-run-{run_id}")
            self._active_thread = t
            t.start()

    def _run_worker(self, run_id: int) -> None:
        geo_svc = get_geography_service()
        log_with_context(logger, logging.INFO, f"Starting collection run {run_id}", run_id=run_id)

        try:
            with db_manager.read_connection() as conn:
                run = dict(conn.execute("SELECT * FROM collection_runs WHERE id = ?;", (run_id,)).fetchone())
                w_codes = json.loads(run["selected_wilayas_json"])
                c_ids = json.loads(run["selected_communes_json"])
                s_keys = json.loads(run["selected_sources_json"])
                checkpoint = json.loads(run["checkpoint_json"] or "{}")

                ph_w = ",".join("?" for _ in w_codes)
                selected_wilayas = [
                    dict(r)
                    for r in conn.execute(
                        f"SELECT code, code_str, name_fr, name_ar, min_lat, max_lat, min_lon, max_lon FROM wilayas WHERE code IN ({ph_w}) ORDER BY code;",
                        w_codes,
                    ).fetchall()
                ]
                selected_communes: list[dict[str, Any]] = []
                if c_ids:
                    ph_c = ",".join("?" for _ in c_ids)
                    selected_communes = [
                        dict(r) for r in conn.execute(f"SELECT * FROM communes WHERE id IN ({ph_c});", c_ids).fetchall()
                    ]
                sources_map = {
                    r["key"]: dict(r)
                    for r in conn.execute("SELECT * FROM sources;").fetchall()
                }

            def is_stop() -> bool:
                return self._stop_event.is_set()

            def save_checkpoint(cp: dict[str, Any]) -> None:
                with db_manager.transaction() as conn:
                    conn.execute(
                        "UPDATE collection_runs SET checkpoint_json = ? WHERE id = ?;",
                        (json.dumps(cp, ensure_ascii=False), run_id),
                    )

            def on_wilaya_status(w_code: int, source_key: str, status: str, count: int, err: str) -> None:
                now = datetime.now(timezone.utc).isoformat()
                with db_manager.transaction() as conn:
                    conn.execute(
                        """
                        UPDATE collection_wilaya_progress
                        SET coverage_status = ?, discovered_count = ?, error_message = ?, updated_at = ?
                        WHERE run_id = ? AND wilaya_code = ? AND source_key = ?;
                        """,
                        (status, count, err, now, run_id, w_code, source_key),
                    )
                    done_tasks = conn.execute(
                        """
                        SELECT COUNT(*) AS cnt FROM collection_wilaya_progress
                        WHERE run_id = ? AND coverage_status NOT IN ('not_started', 'in_progress');
                        """,
                        (run_id,),
                    ).fetchone()["cnt"]
                    conn.execute("UPDATE collection_runs SET completed_tasks = ? WHERE id = ?;", (done_tasks, run_id))

            def on_record(rec: CollectedRawRecord, hint_wilaya_code: int | None) -> None:
                with db_manager.transaction() as conn:
                    outcome = ingest_raw_record(conn, rec, run_id=run_id, geo=geo_svc)
                    # Update run counters
                    new_inc = 1 if outcome.action in ("new", "review_candidate") else 0
                    merged_inc = 1 if outcome.action == "auto_merged" else 0
                    rej_inc = 1 if outcome.action == "rejected" else 0
                    rev_inc = 1 if outcome.needs_review else 0
                    conn.execute(
                        """
                        UPDATE collection_runs
                        SET discovered_count = discovered_count + 1,
                            processed_count = processed_count + 1,
                            new_businesses_count = new_businesses_count + ?,
                            merged_count = merged_count + ?,
                            rejected_count = rejected_count + ?,
                            review_required_count = review_required_count + ?
                        WHERE id = ?;
                        """,
                        (new_inc, merged_inc, rej_inc, rev_inc, run_id),
                    )

                    # Attribute wilaya progress cleanly
                    w_code = hint_wilaya_code
                    if w_code is None and outcome.business_id is not None:
                        b_row = conn.execute("SELECT wilaya_code FROM businesses WHERE id = ?;", (outcome.business_id,)).fetchone()
                        if b_row and b_row["wilaya_code"]:
                            w_code = int(b_row["wilaya_code"])
                    if w_code is not None:
                        now = datetime.now(timezone.utc).isoformat()
                        conn.execute(
                            """
                            UPDATE collection_wilaya_progress
                            SET processed_count = processed_count + 1,
                                rejected_count = rejected_count + ?,
                                review_count = review_count + ?,
                                updated_at = ?
                            WHERE run_id = ? AND wilaya_code = ? AND source_key = ?;
                            """,
                            (rej_inc, rev_inc, now, run_id, w_code, rec.source_key),
                        )

            for sk in s_keys:
                if is_stop():
                    break
                adapter = ADAPTER_REGISTRY.get(sk)
                src_meta = sources_map.get(sk) or {}
                if not adapter:
                    continue
                cfg = json.loads(src_meta.get("config_json") or "{}")
                cfg["rate_limit_seconds"] = src_meta.get("rate_limit_seconds", 1.5)
                cfg["max_retries"] = src_meta.get("max_retries", 3)

                ctx = CollectionContext(
                    run_id=run_id,
                    selected_wilayas=selected_wilayas,
                    selected_communes=selected_communes,
                    search_depth=run["search_depth"],
                    is_stop_requested=is_stop,
                    on_record=on_record,
                    on_wilaya_status=on_wilaya_status,
                    checkpoint=checkpoint,
                    save_checkpoint=save_checkpoint,
                    source_config=cfg,
                )

                log_with_context(logger, logging.INFO, f"Running source adapter '{sk}'", run_id=run_id, source=sk)
                try:
                    res = adapter.collect(ctx)
                    errs = res.get("errors") or []
                    now = datetime.now(timezone.utc).isoformat()
                    status_str = "ok" if not errs else f"partial_errors ({len(errs)})"
                    with db_manager.transaction() as conn:
                        conn.execute(
                            "UPDATE sources SET last_run_at = ?, last_status = ?, last_error = ? WHERE key = ?;",
                            (now, status_str, "\n".join(errs[:5]), sk),
                        )
                        if errs:
                            conn.execute(
                                "UPDATE collection_runs SET error_count = error_count + ? WHERE id = ?;",
                                (len(errs), run_id),
                            )
                        # Mark non-bbox sources (PBF / directories) wilaya coverage honestly as coverage_uncertain if 0 discovered, else collection_completed
                        if sk in ("osm_pbf", "pagesmaghreb", "pagesjaunes_dz", "business_website"):
                            for w in selected_wilayas:
                                wc = int(w["code"])
                                p_row = conn.execute(
                                    "SELECT processed_count, coverage_status FROM collection_wilaya_progress WHERE run_id = ? AND wilaya_code = ? AND source_key = ?;",
                                    (run_id, wc, sk),
                                ).fetchone()
                                if p_row and p_row["coverage_status"] == "not_started":
                                    if p_row["processed_count"] > 0:
                                        cov = "collection_completed"
                                    elif errs:
                                        cov = "sources_unavailable"
                                    else:
                                        cov = "coverage_uncertain" if sk in ("pagesjaunes_dz", "business_website") else "no_results_found"
                                    conn.execute(
                                        "UPDATE collection_wilaya_progress SET coverage_status = ?, updated_at = ? WHERE run_id = ? AND wilaya_code = ? AND source_key = ?;",
                                        (cov, now, run_id, wc, sk),
                                    )
                    if errs:
                        log_with_context(
                            logger,
                            logging.WARNING,
                            f"Source '{sk}' finished with {len(errs)} error(s): {errs[0]}",
                            run_id=run_id,
                            source=sk,
                        )
                except InterruptedError:
                    log_with_context(logger, logging.INFO, f"Source '{sk}' stopped cleanly by user", run_id=run_id)
                    break
                except Exception as exc:
                    now = datetime.now(timezone.utc).isoformat()
                    with db_manager.transaction() as conn:
                        conn.execute(
                            "UPDATE sources SET last_run_at = ?, last_status = 'error', last_error = ? WHERE key = ?;",
                            (now, str(exc), sk),
                        )
                        conn.execute(
                            "UPDATE collection_runs SET error_count = error_count + 1 WHERE id = ?;",
                            (run_id,),
                        )
                    log_with_context(logger, logging.ERROR, f"Source '{sk}' failed: {exc}", run_id=run_id, source=sk)

            final_status = "cancelled" if is_stop() else "completed"
            now = datetime.now(timezone.utc).isoformat()
            with db_manager.transaction() as conn:
                done_tasks = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM collection_wilaya_progress WHERE run_id = ? AND coverage_status NOT IN ('not_started', 'in_progress');",
                    (run_id,),
                ).fetchone()["cnt"]
                conn.execute(
                    "UPDATE collection_runs SET status = ?, finished_at = ?, completed_tasks = ? WHERE id = ?;",
                    (final_status, now, done_tasks, run_id),
                )
            log_with_context(logger, logging.INFO, f"Collection run {run_id} {final_status}", run_id=run_id)
        except Exception as exc:
            now = datetime.now(timezone.utc).isoformat()
            with db_manager.transaction() as conn:
                conn.execute(
                    "UPDATE collection_runs SET status = 'failed', finished_at = ?, notes = ? WHERE id = ?;",
                    (now, f"Fatal error: {exc}", run_id),
                )
            log_with_context(logger, logging.ERROR, f"Collection run {run_id} failed: {exc}", run_id=run_id)
        finally:
            with self._lock:
                self._active_run_id = None


collection_engine = CollectionEngine()
