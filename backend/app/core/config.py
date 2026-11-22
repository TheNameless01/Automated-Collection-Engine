"""Application configuration and safe filesystem path utilities."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _resolve_root_dir() -> Path:
    env_root = (os.environ.get("DZ_ROOT_DIR") or "").strip()
    if env_root:
        candidate = Path(env_root).resolve()
        if (candidate / "backend").is_dir():
            return candidate
    return Path(__file__).resolve().parents[3]


def _env_int(name: str, default: int, min_val: int = 1, max_val: int = 65535) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        val = int(raw)
        if min_val <= val <= max_val:
            return val
    except ValueError:
        pass
    return default


def _env_float(name: str, default: float, min_val: float = 0.0, max_val: float = 120.0) -> float:
    raw = (os.environ.get(name) or "").strip()
    try:
        val = float(raw)
        if min_val <= val <= max_val:
            return val
    except ValueError:
        pass
    return default


def _env_host(name: str, default: str = "127.0.0.1") -> str:
    raw = (os.environ.get(name) or "").strip()
    if raw in ("127.0.0.1", "localhost", "0.0.0.0") or ("." in raw and " " not in raw):
        return raw
    return default


def _env_log_level(name: str, default: str = "INFO") -> str:
    raw = (os.environ.get(name) or "").strip().upper()
    if raw in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return raw
    return default


def _env_url(name: str, default: str) -> str:
    raw = (os.environ.get(name) or "").strip()
    if raw.startswith(("http://", "https://")) and "." in raw:
        return raw
    return default


def _env_user_agent(name: str, default: str) -> str:
    raw = (os.environ.get(name) or "").strip()
    if len(raw) >= 8 and "/" in raw:
        return raw
    return default


@dataclass
class Settings:
    app_name: str = "DZ Car Rental Finder"
    host: str = _env_host("DZ_HOST", "127.0.0.1")
    port: int = _env_int("DZ_PORT", 8000)
    root_dir: Path = field(default_factory=_resolve_root_dir)
    db_path: Path = field(init=False)
    raw_dir: Path = field(init=False)
    processed_dir: Path = field(init=False)
    boundaries_dir: Path = field(init=False)
    backups_dir: Path = field(init=False)
    exports_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    dist_dir: Path = field(init=False)
    user_agent: str = _env_user_agent(
        "DZ_USER_AGENT",
        "DZCarRentalFinder/1.0 (local-open-data-research; respectful-rate-limited)",
    )
    default_rate_limit_seconds: float = _env_float("DZ_DEFAULT_RATE_LIMIT_SECONDS", 1.5)
    osm_pbf_url: str = _env_url(
        "DZ_OSM_PBF_URL",
        "https://download.geofabrik.de/africa/algeria-latest.osm.pbf",
    )
    log_level: str = _env_log_level("DZ_LOG_LEVEL", "INFO")

    def __post_init__(self) -> None:
        self.raw_dir = (self.root_dir / "data" / "raw").resolve()
        self.processed_dir = (self.root_dir / "data" / "processed").resolve()
        self.boundaries_dir = (self.root_dir / "data" / "boundaries").resolve()
        self.backups_dir = (self.root_dir / "data" / "backups").resolve()
        self.exports_dir = (self.root_dir / "exports").resolve()
        self.logs_dir = (self.root_dir / "logs").resolve()
        self.dist_dir = (self.root_dir / "dist").resolve()

        env_db = (os.environ.get("DZ_DB_PATH") or "").strip()
        if env_db and env_db.lower().endswith((".db", ".sqlite", ".sqlite3")):
            p = Path(env_db)
            self.db_path = p.resolve() if p.is_absolute() else (self.root_dir / p).resolve()
        else:
            self.db_path = (self.processed_dir / "dz_car_rental.db").resolve()

        for directory in (
            self.raw_dir,
            self.processed_dir,
            self.boundaries_dir,
            self.backups_dir,
            self.exports_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def safe_resolve_within(base_dir: Path, filename: str) -> Path:
    """Resolve a user-supplied filename strictly inside base_dir, preventing traversal."""
    cleaned = os.path.basename(filename.strip())
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Invalid filename")
    base = base_dir.resolve()
    target = (base / cleaned).resolve()
    if not (str(target).startswith(str(base) + os.sep) or target == base):
        raise ValueError("Path escapes allowed directory")
    return target


settings = Settings()
