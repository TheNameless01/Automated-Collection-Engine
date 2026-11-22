"""Base classes, rate-limited resilient HTTP client, and robots.txt compliance."""

from __future__ import annotations

import logging
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import settings

logger = logging.getLogger("dz_finder.collectors")

CAR_RENTAL_KEYWORDS_RE = re.compile(
    r"(location\s*(de\s*)?(voiture|v[ée]hicule|auto)|loueur\s*auto|rent\s*a\s*car|car\s*(rental|hire)"
    r"|كراء\s*(ال)?سيارات|تأجير\s*(ال)?سيارات|تاجير\s*(ال)?سيارات|تأجير\s*(ال)?مركبات|وكالة\s*كراء)",
    re.IGNORECASE | re.UNICODE,
)


@dataclass
class CollectedRawRecord:
    """Raw evidence extracted from a single source item before normalization/dedup."""

    source_key: str
    external_id: str
    source_url: str = ""
    raw_name: str = ""
    raw_name_ar: str = ""
    raw_name_fr: str = ""
    raw_name_en: str = ""
    raw_phones: list[str] = field(default_factory=list)
    raw_address: str = ""
    raw_commune: str = ""
    raw_wilaya: str = ""
    raw_lat: float | None = None
    raw_lon: float | None = None
    raw_website: str = ""
    raw_facebook: str = ""
    raw_instagram: str = ""
    raw_other_socials: list[str] = field(default_factory=list)
    raw_google_maps_url: str = ""
    attribution_text: str = ""
    notes: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectionContext:
    run_id: int
    selected_wilayas: list[dict[str, Any]]
    selected_communes: list[dict[str, Any]]
    search_depth: str  # quick | standard | deep
    is_stop_requested: Callable[[], bool]
    on_record: Callable[[CollectedRawRecord, int | None], None]
    on_wilaya_status: Callable[[int, str, str, int, str], None]  # wilaya_code, source_key, status, count, error
    checkpoint: dict[str, Any]
    save_checkpoint: Callable[[dict[str, Any]], None]
    source_config: dict[str, Any] = field(default_factory=dict)


class RobotsTxtCache:
    """Caches and evaluates robots.txt rules per origin without bypassing restrictions."""

    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._cache: dict[str, tuple[float, RobotFileParser | None]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, url: str, client: httpx.Client) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False
        origin = f"{parsed.scheme}://{parsed.netloc}"
        now = time.monotonic()

        with self._lock:
            cached = self._cache.get(origin)
            if cached and (now - cached[0]) < 3600:
                rp = cached[1]
                return True if rp is None else rp.can_fetch(self.user_agent, url)

        robots_url = f"{origin}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            resp = client.get(robots_url, timeout=10.0)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                allowed = rp.can_fetch(self.user_agent, url)
            elif resp.status_code in (401, 403):
                # Forbidden to read robots.txt -> treat conservatively as disallowed
                rp = None
                allowed = False
            else:
                rp = None
                allowed = True
        except Exception:
            rp = None
            allowed = True

        with self._lock:
            self._cache[origin] = (now, rp)
        return allowed


class ResilientHttpClient:
    """Rate-limited HTTP client with exponential backoff and robots.txt enforcement."""

    def __init__(
        self,
        *,
        rate_limit_seconds: float = 1.5,
        max_retries: int = 3,
        timeout_seconds: float = 20.0,
        respect_robots: bool = True,
        user_agent: str | None = None,
    ) -> None:
        self.rate_limit_seconds = max(0.0, rate_limit_seconds)
        self.max_retries = max(0, max_retries)
        self.respect_robots = respect_robots
        self.user_agent = user_agent or settings.user_agent
        self._last_request_by_host: dict[str, float] = {}
        self._lock = threading.Lock()
        self._robots = RobotsTxtCache(self.user_agent)
        self._client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent, "Accept-Language": "fr-DZ,fr;q=0.9,ar-DZ;q=0.8,en;q=0.7"},
        )

    def close(self) -> None:
        self._client.close()

    def _wait_rate_limit(self, host: str, stop_fn: Callable[[], bool] | None = None) -> None:
        if self.rate_limit_seconds <= 0:
            return
        with self._lock:
            last = self._last_request_by_host.get(host, 0.0)
            elapsed = time.monotonic() - last
            wait_s = self.rate_limit_seconds - elapsed
            if wait_s > 0:
                # Sleep in short slices so stop requests respond promptly
                slept = 0.0
                while slept < wait_s:
                    if stop_fn and stop_fn():
                        return
                    chunk = min(0.25, wait_s - slept)
                    time.sleep(chunk)
                    slept += chunk
            self._last_request_by_host[host] = time.monotonic()

    def request(
        self,
        method: str,
        url: str,
        *,
        stop_fn: Callable[[], bool] | None = None,
        check_robots: bool | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        if stop_fn and stop_fn():
            raise InterruptedError("Collection stop requested")

        enforce_robots = self.respect_robots if check_robots is None else check_robots
        if enforce_robots and not self._robots.is_allowed(url, self._client):
            raise PermissionError(f"Blocked by robots.txt: {url}")

        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if stop_fn and stop_fn():
                raise InterruptedError("Collection stop requested")
            self._wait_rate_limit(host, stop_fn)
            try:
                resp = self._client.request(method, url, **kwargs)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    backoff = min(30.0, (2 ** attempt) * max(1.0, self.rate_limit_seconds))
                    time.sleep(backoff)
                    continue
                return resp
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    backoff = min(30.0, (2 ** attempt) * 1.5)
                    time.sleep(backoff)
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Request failed: {url}")


class BaseSourceAdapter(ABC):
    key: str = ""
    name: str = ""

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        """Verify source availability without bypassing access controls."""

    @abstractmethod
    def collect(self, ctx: CollectionContext) -> dict[str, Any]:
        """Run collection across requested wilayas and emit CollectedRawRecord items."""
