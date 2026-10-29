"""
HTTP client for The Odds API v4 with on-disk response caching.

Never log or print the API key.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "odds_api"
NBA_SPORT_KEY = "basketball_nba"


class OddsApiClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        cache_dir: Optional[Path] = None,
        session: Optional[requests.Session] = None,
        use_cache: bool = True,
    ):
        if not api_key:
            raise ValueError("ODDS_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.session = session or requests.Session()
        self.use_cache = use_cache
        self.last_requests_remaining: Optional[str] = None

    def _cache_path(self, *parts: str) -> Path:
        return self.cache_dir.joinpath(*parts)

    def _read_cache(self, path: Path) -> Optional[Any]:
        if not self.use_cache or not path.is_file():
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
        resp = self.session.request(method, url, params=query, timeout=30)
        remaining = resp.headers.get("x-requests-remaining")
        if remaining is not None:
            self.last_requests_remaining = remaining
            logger.info("The Odds API x-requests-remaining: %s", remaining)
        resp.raise_for_status()
        data = resp.json()
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
