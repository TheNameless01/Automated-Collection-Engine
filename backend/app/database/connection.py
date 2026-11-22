"""SQLite database connection management, transactions, backups, and integrity checks."""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.core.config import safe_resolve_within, settings


class DatabaseManager:
    """Thread-safe SQLite connection and backup manager."""

    def __init__(self, db_path: Path | None = None, backups_dir: Path | None = None) -> None:
        self.db_path = (db_path or settings.db_path).resolve()
        self.backups_dir = (backups_dir or settings.backups_dir).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def read_connection(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    def create_backup(self, reason: str = "manual") -> Path | None:
        """Create a consistent SQLite hot backup using sqlite3.Connection.backup."""
        if not self.db_path.exists():
            return None
        safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in reason)[:40]
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"dz_car_rental_{ts}_{safe_reason}.db"
        backup_path = safe_resolve_within(self.backups_dir, backup_name)
        src = sqlite3.connect(str(self.db_path), timeout=30.0)
        dst = sqlite3.connect(str(backup_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return backup_path

    def restore_backup(self, backup_filename: str) -> Path:
        """Restore database from a named backup file after creating a safety snapshot."""
        backup_path = safe_resolve_within(self.backups_dir, backup_filename)
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_filename}")

        # Validate backup integrity first
        check_conn = sqlite3.connect(str(backup_path))
        try:
            row = check_conn.execute("PRAGMA integrity_check;").fetchone()
            if not row or row[0] != "ok":
                raise ValueError("Backup file failed SQLite integrity_check")
        finally:
            check_conn.close()

        if self.db_path.exists():
            self.create_backup(reason="pre_restore_safety")

        # Remove WAL/SHM sidecars if present before replacing main db file
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.db_path) + suffix)
            if sidecar.exists():
                sidecar.unlink()

        shutil.copy2(backup_path, self.db_path)
        return self.db_path

    def list_backups(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for p in sorted(self.backups_dir.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True):
            stat = p.stat()
            items.append(
                {
                    "filename": p.name,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
        return items

    def integrity_check(self) -> dict[str, object]:
        with self.read_connection() as conn:
            res = conn.execute("PRAGMA integrity_check;").fetchall()
            messages = [r[0] for r in res]
            fk_issues = conn.execute("PRAGMA foreign_key_check;").fetchall()
        return {
            "ok": messages == ["ok"] and len(fk_issues) == 0,
            "integrity_messages": messages,
            "foreign_key_violations": len(fk_issues),
        }


db_manager = DatabaseManager()
