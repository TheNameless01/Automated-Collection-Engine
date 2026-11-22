"""Pytest fixtures isolating every test from production SQLite database files."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.database.connection import DatabaseManager
from app.database.migrations import run_migrations
from app.geography.service import GeographyService


@pytest.fixture()
def temp_db(tmp_path: Path) -> Iterator[DatabaseManager]:
    db_file = tmp_path / "test_dz.db"
    backups_dir = tmp_path / "backups"
    mgr = DatabaseManager(db_path=db_file, backups_dir=backups_dir)
    run_migrations(mgr, settings.boundaries_dir)
    yield mgr


@pytest.fixture(scope="session")
def geo_service() -> GeographyService:
    return GeographyService(settings.boundaries_dir)
