"""NFL suggested-bet eligibility: usage-first (starters when lineup data exists)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Game, Player, PlayerGameStat
from app.models.lineup import Lineup


def _recent_game_stats(
    db: Session, player_id: int, lookback_games: int = 8
) -> list:
    cutoff = date.today() - timedelta(days=220)
    return (
        db.query(PlayerGameStat, Game)
        .join(Game, PlayerGameStat.game_id == Game.game_id)
        .filter(
            PlayerGameStat.player_id == player_id,
            Game.sport == "NFL",
            Game.game_status == "finished",
            Game.game_date >= cutoff,
        )
        .order_by(Game.game_date.desc())
        .limit(lookback_games)
        .all()
    )


def _usage_averages(rows: list, stat_type: str) -> dict:
    if not rows:
        return {}
    n = len(rows)
    pa = sum((s.pass_attempts or 0) for s, _ in rows) / n
    ra = sum((s.rushing_attempts or 0) for s, _ in rows) / n
    tg = sum((s.targets or 0) for s, _ in rows) / n
    rec = sum((s.receptions or 0) for s, _ in rows) / n
    snaps = [float(s.snap_percentage) for s, _ in rows if s.snap_percentage and s.snap_percentage > 0]
    return {
        "pass_attempts": pa,
        "rush_attempts": ra,
        "targets": tg,
        "receptions": rec,
        "avg_snap": sum(snaps) / len(snaps) if snaps else None,
        "n": n,
    }


def _meets_usage_threshold(stat_type: str, usage: dict) -> bool:
    if stat_type in ("passing_yards", "completions", "attempts", "pass_attempts"):
        return usage.get("pass_attempts", 0) >= 14.0
    if stat_type in ("rushing_yards", "rushing_attempts"):
        return usage.get("rush_attempts", 0) >= 5.0
    if stat_type in ("receptions", "receiving_yards", "targets"):
        return usage.get("targets", 0) >= 3.0 or usage.get("receptions", 0) >= 2.0
    if stat_type == "anytime_td":
        return usage.get("rush_attempts", 0) >= 2.0 or usage.get("targets", 0) >= 2.0
    return True


def _recent_starter_rate(db: Session, player_id: int, lookback: int = 8) -> Tuple[float, int]:
    cutoff = date.today() - timedelta(days=220)
    rows = (
        db.query(Lineup, Game)
        .join(Game, Lineup.game_id == Game.game_id)
        .filter(
            Lineup.player_id == player_id,
            Game.sport == "NFL",
            Game.game_status == "finished",
            Game.game_date >= cutoff,
        )
        .order_by(Game.game_date.desc())
        .limit(lookback)
        .all()
    )
    if not rows:
        return 0.0, 0
    return sum(1 for lu, _ in rows if lu.is_starter) / len(rows), len(rows)


def nfl_player_role_eligible(
    db: Session,
    player_id: int,
    stat_type: str,
    min_games: int = 5,
    min_snap_pct: float = 22.0,
    lookback_games: int = 8,
    game_id: Optional[int] = None,
) -> Tuple[bool, str]:
    if game_id is not None:
        from app.services.lineup_service import LineupService

        if LineupService(db).is_player_starter(game_id, player_id):
            return True, "confirmed_starter"

    rows = _recent_game_stats(db, player_id, lookback_games)
    if len(rows) < min_games:
        return False, f"only {len(rows)} recent games (need {min_games})"

    usage = _usage_averages(rows, stat_type)
    if not _meets_usage_threshold(stat_type, usage):
        return False, "below usage threshold for stat role"

    avg_snap = usage.get("avg_snap")
    if avg_snap is not None and avg_snap < min_snap_pct:
        starter_rate, starter_n = _recent_starter_rate(db, player_id)
        if starter_n >= 2 and starter_rate >= 0.35:
            pass
        elif avg_snap < min_snap_pct - 5:
            return False, f"avg snap {avg_snap:.0f}% too low"

    return True, "ok"
