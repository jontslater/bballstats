"""
HTTP client for The Odds API v4 with on-disk response caching.

Never log or print the API key.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "odds_api"
DEFAULT_CACHE_TTL_SECONDS = 3600
NBA_SPORT_KEY = "basketball_nba"


class OddsApiError(Exception):
    """Raised for Odds API failures without leaking credentials."""


def _redact_api_key(text: str, api_key: str) -> str:
    if not text or not api_key:
        return text or ""
    return text.replace(api_key, "***REDACTED***")


class OddsApiClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        cache_dir: Optional[Path] = None,
        session: Optional[requests.Session] = None,
        use_cache: bool = True,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        force_refresh: bool = False,
    ):
        if not api_key:
            raise ValueError("ODDS_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.session = session or requests.Session()
        self.use_cache = use_cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self.force_refresh = force_refresh
        self.last_requests_remaining: Optional[str] = None

    def _cache_path(self, *parts: str) -> Path:
        return self.cache_dir.joinpath(*parts)

    def _cache_is_fresh(self, path: Path) -> bool:
        if self.force_refresh or not path.is_file():
            return False
        age = time.time() - path.stat().st_mtime
        return age <= self.cache_ttl_seconds

    def _read_cache(self, path: Path) -> Optional[Any]:
        if not self.use_cache or not self._cache_is_fresh(path):
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _write_cache(self, path: Path, payload: Any) -> None:
        if not self.use_cache:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
        cache_file: Optional[Path] = None,
    ) -> Tuple[Optional[Any], bool]:
        """
        Returns (json_payload, from_cache).
        """
        if cache_file:
            cached = self._read_cache(cache_file)
            if cached is not None:
                return cached, True

        query = dict(params or {})
        query["apiKey"] = self.api_key
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(method, url, params=query, timeout=30)
        except requests.RequestException as exc:
            raise OddsApiError(f"Odds API request failed for {path}: {exc}") from exc

        remaining = resp.headers.get("x-requests-remaining")
        if remaining is not None:
            self.last_requests_remaining = remaining
            logger.info("The Odds API x-requests-remaining: %s", remaining)

        if resp.status_code >= 400:
            body = _redact_api_key(resp.text[:500], self.api_key)
            raise OddsApiError(
                f"Odds API HTTP {resp.status_code} for {path}: {body}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise OddsApiError(f"Odds API returned invalid JSON for {path}") from exc

        if cache_file:
            self._write_cache(cache_file, data)
        return data, False

    @staticmethod
    def _markets_slug(markets: List[str]) -> str:
        return re.sub(r"[^a-z0-9]+", "_", "_".join(sorted(markets)))

    def fetch_nba_events(self, cache_date: str) -> Tuple[List[Dict[str, Any]], bool]:
        cache_file = self._cache_path(cache_date, "events.json")
        data, from_cache = self._request(
            "GET",
            f"/sports/{NBA_SPORT_KEY}/events",
            cache_file=cache_file,
        )
        if not isinstance(data, list):
            return [], from_cache
        return data, from_cache

    def fetch_event_odds(
        self,
        event_id: str,
        markets: List[str],
        bookmakers: List[str],
        cache_date: str,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        cache_file = self._cache_path(
            cache_date,
            f"odds_{event_id}_{self._markets_slug(markets)}.json",
        )
        params = {
            "regions": "us",
            "markets": ",".join(markets),
            "bookmakers": ",".join(bookmakers),
            "oddsFormat": "american",
        }
        data, from_cache = self._request(
            "GET",
            f"/sports/{NBA_SPORT_KEY}/events/{event_id}/odds",
            params=params,
            cache_file=cache_file,
        )
        if not isinstance(data, dict):
            return None, from_cache
        return data, from_cache
