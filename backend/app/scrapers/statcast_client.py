"""
Baseball Savant Statcast CSV client (free, no API key).

Fetches game-day batted-ball detail rows used to build leak-free cumulative
expected-stat profiles for walk-forward backtests.
"""
from __future__ import annotations

import csv
import io
import time
from datetime import date, timedelta
from typing import Dict, Iterator, List, Optional

import requests

STATCAST_SEARCH_URL = "https://baseballsavant.mlb.com/statcast_search/csv"

# Outcomes that put a ball in play with a recorded launch speed
HIT_EVENTS = {
    "single",
    "double",
    "triple",
    "home_run",
    "field_out",
    "force_out",
    "grounded_into_double_play",
    "fielders_choice",
    "fielders_choice_out",
    "sac_fly",
    "sac_bunt",
    "double_play",
    "triple_play",
    "field_error",
}

TB_BY_EVENT = {
    "single": 1,
    "double": 2,
    "triple": 3,
    "home_run": 4,
}


class StatcastClient:
    """Minimal client for Savant statcast_search CSV exports."""

    def __init__(self, delay: float = 1.0, timeout: float = 120.0):
        self.delay = delay
        self.timeout = timeout
        self._last_call = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "nba-betting-research/1.0 (MLB statcast ingestion)",
                "Accept": "text/csv",
            }
        )

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def fetch_batted_balls_for_date(self, game_date: date, season: int) -> List[Dict]:
        """
        Return batted-ball rows for one calendar day (regular + postseason).

        Each dict includes batter mlbam id and estimated/actual contact metrics.
        """
        self._rate_limit()
        next_day = game_date + timedelta(days=1)
        params = {
            "all": "true",
            "hfGT": "R|",
            "hfSea": f"{season}|",
            "player_type": "batter",
            "game_date_gt": game_date.isoformat(),
            "game_date_lt": next_day.isoformat(),
            "min_pitches": "0",
            "min_results": "0",
            "type": "details",
        }
        response = self.session.get(
            STATCAST_SEARCH_URL, params=params, timeout=self.timeout
        )
        response.raise_for_status()
        return list(self._parse_csv(response.text))

    def fetch_expected_stats_leaderboard_csv(self, season: int, min_pa: int = 10) -> str:
        """
        Season-to-date expected stats CSV (Savant leaderboard).

        WARNING: Using this snapshot for historical backtests introduces lookahead
        unless as_of_date equals the prediction date. Prefer daily batted-ball rollups.
        """
        self._rate_limit()
        url = (
            "https://baseballsavant.mlb.com/leaderboard/expected_statistics"
            f"?type=batter&year={season}&position=&team=&min={min_pa}"
            "&sort=xba&sortDir=desc&csv=true"
        )
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def _parse_csv(self, text: str) -> Iterator[Dict]:
        if not text or not text.strip():
            return
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            yield self._normalize_row(row)

    def _normalize_row(self, row: Dict) -> Dict:
        batter_raw = row.get("batter") or row.get("player_id") or ""
        try:
            batter_id = int(batter_raw)
        except (TypeError, ValueError):
            batter_id = 0

        launch_speed = self._to_float(row.get("launch_speed"))
        est_ba = self._to_float(row.get("estimated_ba_using_speedangle"))
        est_slg = self._to_float(row.get("estimated_slg_using_speedangle"))
        est_woba = self._to_float(row.get("estimated_woba_using_speedangle"))
        events = (row.get("events") or "").strip().lower()
        lsa = self._to_int(row.get("launch_speed_angle"))

        is_bip = launch_speed is not None and events in HIT_EVENTS
        tb = TB_BY_EVENT.get(events, 0)
        is_hit = events in {"single", "double", "triple", "home_run"}

        return {
            "batter_id": batter_id,
            "game_date": row.get("game_date"),
            "events": events,
            "is_bip": is_bip,
            "is_hit": is_hit,
            "total_bases": tb,
            "launch_speed": launch_speed,
            "launch_speed_angle": lsa,
            "est_ba": est_ba if est_ba is not None else 0.0,
            "est_slg": est_slg if est_slg is not None else 0.0,
            "est_woba": est_woba if est_woba is not None else 0.0,
        }

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
