"""
NBA data client: ESPN primary, optional nba_api fallback for box scores.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Dict, List, Optional

from .espn_nba_client import ESPNNBAClient

try:
    from nba_api.stats.endpoints import boxscoretraditionalv2
    from nba_api.stats.static import teams

    NBA_API_AVAILABLE = True
except ImportError:
    NBA_API_AVAILABLE = False
    teams = None
    boxscoretraditionalv2 = None


class NBAAPIClient:
    """Client for NBA schedule and box scores."""

    def __init__(self, delay: float = 0.6, use_nba_api_fallback: bool = True):
        self.delay = delay
        self.last_call_time = 0.0
        self.espn = ESPNNBAClient(delay=delay)
        self.use_nba_api_fallback = use_nba_api_fallback and NBA_API_AVAILABLE

    def _rate_limit(self) -> None:
        current = time.time()
        if current - self.last_call_time < self.delay:
            time.sleep(self.delay - (current - self.last_call_time))
        self.last_call_time = time.time()

    def get_game_schedule(self, game_date: date) -> List[Dict]:
        games = self.espn.get_games_for_date(game_date)
        legacy = []
        status_map = {"scheduled": 1, "in_progress": 2, "finished": 3, "cancelled": 1}
        for g in games:
            legacy.append(
                {
                    "GAME_ID": g["espn_game_id"],
                    "GAME_DATE": g["game_date"].strftime("%Y-%m-%d"),
                    "GAME_STATUS_TEXT": g.get("status_name", g.get("status", "")),
                    "GAME_STATUS_ID": status_map.get(g.get("status", "scheduled"), 1),
                    "HOME_TEAM_ID": g.get("home_team"),
                    "VISITOR_TEAM_ID": g.get("away_team"),
                    "HOME_TEAM_SCORE": g.get("home_score"),
                    "VISITOR_TEAM_SCORE": g.get("away_score"),
                    "_espn": g,
                }
            )
        return legacy

    def get_game_box_score(self, game_id: str) -> Optional[Dict]:
        box = self.espn.get_box_score_for_game(str(game_id))
        if box and box.get("player_stats"):
            return self._espn_to_legacy_box(box)

        if not self.use_nba_api_fallback:
            return None

        self._rate_limit()
        try:
            bs = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id, timeout=60)
            player_stats_df = bs.get_data_frames()[0]
            return {"player_stats": player_stats_df.to_dict("records"), "team_stats": []}
        except Exception:
            return None

    @staticmethod
    def _espn_to_legacy_box(box: Dict) -> Dict:
        player_stats = []
        for ps in box.get("player_stats", []):
            player_stats.append(
                {
                    "PLAYER_ID": ps.get("espn_player_id"),
                    "PLAYER_NAME": ps.get("player_name"),
                    "TEAM_ABBREVIATION": ps.get("team_abbreviation"),
                    "MIN": ps.get("minutes_played"),
                    "PTS": ps.get("points"),
                    "REB": ps.get("rebounds"),
                    "OREB": ps.get("offensive_rebounds"),
                    "DREB": ps.get("defensive_rebounds"),
                    "AST": ps.get("assists"),
                    "STL": ps.get("steals"),
                    "BLK": ps.get("blocks"),
                    "TOV": ps.get("turnovers"),
                    "PF": ps.get("personal_fouls"),
                    "FGM": ps.get("field_goals_made"),
                    "FGA": ps.get("field_goals_attempted"),
                    "FG3M": ps.get("three_pointers_made"),
                    "FG3A": ps.get("three_pointers_attempted"),
                    "FTM": ps.get("free_throws_made"),
                    "FTA": ps.get("free_throws_attempted"),
                    "PLUS_MINUS": ps.get("plus_minus"),
                }
            )
        return {"player_stats": player_stats, "team_stats": [], "injuries": box.get("injuries", [])}

    def get_all_teams(self) -> List[Dict]:
        if NBA_API_AVAILABLE and teams:
            self._rate_limit()
            try:
                return teams.get_teams()
            except Exception:
                pass
        return []
