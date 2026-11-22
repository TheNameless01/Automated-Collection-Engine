"""Initialize SQLite database, run migrations, and verify integrity."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.database.connection import db_manager
from app.database.migrations import run_migrations


def main() -> None:
    run_migrations(db_manager, settings.boundaries_dir)
    check = db_manager.integrity_check()
    with db_manager.read_connection() as conn:
        w = conn.execute("SELECT COUNT(*) FROM wilayas;").fetchone()[0]
        c = conn.execute("SELECT COUNT(*) FROM communes;").fetchone()[0]
        s = conn.execute("SELECT COUNT(*) FROM sources;").fetchone()[0]
    print(f"Database ready at {db_manager.db_path}")
    print(f"Wilayas: {w}, Communes: {c}, Sources: {s}, Integrity OK: {check['ok']}")


if __name__ == "__main__":
    main()
