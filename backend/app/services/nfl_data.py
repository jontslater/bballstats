"""
NFL historical data helpers (nflverse CSV + stats_player parquet).

- Legacy: player_stats.csv (through ~2024)
- Current: stats_player_week_{season}.parquet (2025+)
"""
from __future__ import annotations

import io
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests

NFLVERSE_GAMES_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
)
NFLVERSE_PLAYER_STATS_LEGACY_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"
)
NFLVERSE_STATS_PLAYER_WEEK_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.parquet"
)

NFLVERSE_LEGACY_MAX_SEASON = 2024
NFLVERSE_MODERN_MIN_SEASON = 2025

NFLVERSE_TEAM_MAP = {
    "LA": "LAR",
    "STL": "LAR",
    "OAK": "LV",
    "SD": "LAC",
}


def normalize_team_abbrev(abbrev: str) -> str:
    if not abbrev:
        return abbrev
    ab = str(abbrev).upper()
    return NFLVERSE_TEAM_MAP.get(ab, ab)


def fetch_csv(url: str, timeout: int = 120) -> pd.DataFrame:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return pd.read_csv(io.BytesIO(response.content))


def fetch_parquet(url: str, timeout: int = 120) -> pd.DataFrame:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return pd.read_parquet(io.BytesIO(response.content))


def _normalize_modern_player_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Map stats_player schema to legacy column names used by backfill."""
    out = df.copy()
    if "team" in out.columns and "recent_team" not in out.columns:
        out["recent_team"] = out["team"]
    if "passing_interceptions" in out.columns and "interceptions" not in out.columns:
        out["interceptions"] = out["passing_interceptions"]
    if "carries" in out.columns and "rushing_attempts" not in out.columns:
        out["rushing_attempts"] = out["carries"]
    out["recent_team"] = out["recent_team"].map(normalize_team_abbrev)
    out["opponent_team"] = out["opponent_team"].map(normalize_team_abbrev)
    return out


def _normalize_legacy_player_stats(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["recent_team"] = out["recent_team"].map(normalize_team_abbrev)
    out["opponent_team"] = out["opponent_team"].map(normalize_team_abbrev)
    if "carries" in out.columns and "rushing_attempts" not in out.columns:
        out["rushing_attempts"] = out["carries"]
    return out


def load_nflverse_games(seasons: Iterable[int]) -> pd.DataFrame:
    df = fetch_csv(NFLVERSE_GAMES_URL)
    season_set = {int(s) for s in seasons}
    df = df[df["season"].isin(season_set)].copy()
    df["gameday"] = pd.to_datetime(df["gameday"]).dt.date
    df["away_team"] = df["away_team"].map(normalize_team_abbrev)
    df["home_team"] = df["home_team"].map(normalize_team_abbrev)
    return df


def load_nflverse_player_stats(seasons: Iterable[int]) -> pd.DataFrame:
    season_set = {int(s) for s in seasons}
    frames: List[pd.DataFrame] = []

    legacy_seasons = [s for s in season_set if s <= NFLVERSE_LEGACY_MAX_SEASON]
    modern_seasons = [s for s in season_set if s >= NFLVERSE_MODERN_MIN_SEASON]

    if legacy_seasons:
        legacy = fetch_csv(NFLVERSE_PLAYER_STATS_LEGACY_URL)
        legacy = legacy[legacy["season"].isin(legacy_seasons)]
        frames.append(_normalize_legacy_player_stats(legacy))

    for season in sorted(modern_seasons):
        url = NFLVERSE_STATS_PLAYER_WEEK_URL.format(season=season)
        try:
            modern = fetch_parquet(url)
            modern = modern[modern["season"] == season]
            frames.append(_normalize_modern_player_stats(modern))
        except Exception as exc:
            raise RuntimeError(f"Failed to load nflverse stats_player week file for {season}: {exc}") from exc

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def game_lookup_key(home: str, away: str, game_date: date) -> Tuple[str, str, date]:
    return (normalize_team_abbrev(home), normalize_team_abbrev(away), game_date)


def parse_espn_status(raw: str) -> str:
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
    if probability is None or probability <= 0 or probability >= 1:
        return None
    return int(round(-100.0 * probability / (1.0 - probability)))
