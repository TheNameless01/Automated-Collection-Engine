"""Structured logging configuration (file + SQLite log persistence)."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class SQLiteLogHandler(logging.Handler):
    """Persists INFO+ application logs into SQLite app_logs table safely."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(level=logging.INFO)
        self.db_path = db_path

    def emit(self, record: logging.LogRecord) -> None:
        if not self.db_path.exists():
            return
        try:
            ctx: dict[str, Any] = {}
            if hasattr(record, "context") and isinstance(record.context, dict):
                ctx = record.context
            run_id = getattr(record, "run_id", None)
            now = datetime.now(timezone.utc).isoformat()
            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            try:
                conn.execute(
                    """
                    INSERT INTO app_logs (level, logger_name, message, context_json, run_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.levelname,
                        record.name,
                        self.format(record),
                        json.dumps(ctx, ensure_ascii=False),
                        run_id,
                        now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            # Never crash caller on logging failure
            pass


def setup_logging(logs_dir: Path, db_path: Path, level: str = "INFO") -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger("dz_finder")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        logs_dir / "dz_car_rental.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    root_logger.addHandler(console_handler)

    db_handler = SQLiteLogHandler(db_path)
    db_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(db_handler)

    return root_logger


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    run_id: int | None = None,
    **context: Any,
) -> None:
    logger.log(level, message, extra={"run_id": run_id, "context": context})
