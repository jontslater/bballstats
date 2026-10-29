"""
In-memory player game stat history for fast PIT backtests (rolling medians, sampling).
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models import Game, PlayerGameStat


def stat_value_from_row(stat_row: PlayerGameStat, stat_type: str) -> Optional[float]:
    if stat_type == "points":
        return float(stat_row.points or 0)
    if stat_type == "rebounds":
        return float(stat_row.rebounds or 0)
    if stat_type == "assists":
        return float(stat_row.assists or 0)
    if stat_type == "three_pointers_made":
        return float(stat_row.three_pointers_made or 0)
    if stat_type == "pts+ast+reb":
        return float(
            (stat_row.points or 0)
            + (stat_row.rebounds or 0)
            + (stat_row.assists or 0)
        )
    return None


@dataclass(frozen=True)
class PitCandidate:
    game_id: int
    player_id: int
    stat_type: str
    game_date: date
    actual: float


class PlayerStatHistoryCache:
    """Preloaded finished-game logs for selected seasons."""

    def __init__(self, db: Session, season_ids: Sequence[int]) -> None:
        self._dates: Dict[int, List[date]] = {}
        self._values: Dict[Tuple[int, str], List[float]] = {}
        rows = (
            db.query(PlayerGameStat, Game)
            .join(Game, Game.game_id == PlayerGameStat.game_id)
            .filter(
                PlayerGameStat.sport == "NBA",
                Game.season_id.in_(list(season_ids)),
                Game.game_status == "finished",
                PlayerGameStat.minutes_played > 0,
            )
            .order_by(Game.game_date.asc())
            .all()
        )
        for stat_row, game in rows:
            pid = stat_row.player_id
            self._dates.setdefault(pid, []).append(game.game_date)
            for st in (
                "points",
                "rebounds",
                "assists",
                "three_pointers_made",
                "pts+ast+reb",
            ):
                v = stat_value_from_row(stat_row, st)
                if v is None:
                    continue
                key = (pid, st)
                self._values.setdefault(key, []).append(float(v))

    def rolling_median(
        self,
        player_id: int,
        stat_type: str,
        before_date: date,
        *,
        window: int = 20,
        min_samples: int = 3,
    ) -> Optional[float]:
        dates = self._dates.get(player_id)
        values = self._values.get((player_id, stat_type))
        if not dates or not values or len(dates) != len(values):
            return None
        idx = bisect_left(dates, before_date)
        if idx <= min_samples:
            return None
        start = max(0, idx - window)
        slice_vals = values[start:idx]
        if len(slice_vals) < min_samples:
            return None
        return float(median(slice_vals))
