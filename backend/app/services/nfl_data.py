"""
NFL historical data helpers (nflverse CSV + ESPN IDs).

Uses free nflverse release assets (no paid API, no nfl_data_py dependency).
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests

NFLVERSE_GAMES_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
)
NFLVERSE_PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"
)

# Map nflverse team codes to our DB abbreviations (LA was RAM before LAR)
NFLVERSE_TEAM_MAP = {
    "LA": "LAR",
    "STL": "LAR",
    "OAK": "LV",
    "SD": "LAC",
}


def normalize_team_abbrev(abbrev: str) -> str:
    if not abbrev:
        return abbrev
    ab = abbrev.upper()
    return NFLVERSE_TEAM_MAP.get(ab, ab)


def fetch_csv(url: str, timeout: int = 120) -> pd.DataFrame:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return pd.read_csv(io.BytesIO(response.content))


def load_nflverse_games(seasons: Iterable[int]) -> pd.DataFrame:
    df = fetch_csv(NFLVERSE_GAMES_URL)
    season_set = {int(s) for s in seasons}
    df = df[df["season"].isin(season_set)].copy()
    df["gameday"] = pd.to_datetime(df["gameday"]).dt.date
    df["away_team"] = df["away_team"].map(normalize_team_abbrev)
    df["home_team"] = df["home_team"].map(normalize_team_abbrev)
    return df


def load_nflverse_player_stats(seasons: Iterable[int]) -> pd.DataFrame:
    df = fetch_csv(NFLVERSE_PLAYER_STATS_URL)
    season_set = {int(s) for s in seasons}
    df = df[df["season"].isin(season_set)].copy()
    df["recent_team"] = df["recent_team"].map(normalize_team_abbrev)
    df["opponent_team"] = df["opponent_team"].map(normalize_team_abbrev)
    return df


def game_lookup_key(home: str, away: str, game_date: date) -> Tuple[str, str, date]:
    return (normalize_team_abbrev(home), normalize_team_abbrev(away), game_date)


def parse_espn_status(raw: str) -> str:
    """Map ESPN status strings to our game_status values."""
    if not raw:
        return "scheduled"
    upper = raw.upper()
    if "FINAL" in upper or upper == "STATUS_FINAL":
        return "finished"
    if "IN_PROGRESS" in upper or "HALFTIME" in upper:
        return "in_progress"
    if "POSTPONED" in upper or "CANCEL" in upper:
        return "cancelled"
    return "scheduled"


def map_espn_injury_status(raw: str) -> str:
    if not raw:
        return "Questionable"
    lower = raw.lower()
    if "out" in lower:
        return "Out"
    if "doubt" in lower:
        return "Doubtful"
    if "question" in lower:
        return "Questionable"
    if "prob" in lower:
        return "Probable"
    return "Questionable"


def american_break_even_odds(probability: float) -> Optional[int]:
    """
    Break-even American odds for an OVER at calibrated probability p.

    Owner formula: -100 * p / (1 - p)  (used for typical safe picks with p >= 0.5).
    """
    if probability is None or probability <= 0 or probability >= 1:
        return None
    return int(round(-100.0 * probability / (1.0 - probability)))
