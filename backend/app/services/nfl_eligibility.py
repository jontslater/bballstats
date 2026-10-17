"""NFL suggested-bet eligibility: primary roles via snaps or depth-chart starter."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Game, Player, PlayerGameStat
from app.models.betting_line import BettingLine
from app.models.lineup import Lineup

SNAP_MIN_WR_TE = 50.0
SNAP_MIN_RB = 40.0
SNAP_MIN_QB = 40.0
STARTER_RATE_MIN = 0.5
STARTER_GAMES_MIN = 4


def _recent_game_stats(db: Session, player_id: int, lookback_games: int = 8) -> list:
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


def _usage_averages(rows: list) -> dict:
    if not rows:
        return {}
    n = len(rows)
    snaps = [float(s.snap_percentage) for s, _ in rows if s.snap_percentage and s.snap_percentage > 0]
    return {
        "pass_attempts": sum((s.pass_attempts or 0) for s, _ in rows) / n,
        "rush_attempts": sum((s.rushing_attempts or 0) for s, _ in rows) / n,
        "targets": sum((s.targets or 0) for s, _ in rows) / n,
        "receptions": sum((s.receptions or 0) for s, _ in rows) / n,
        "avg_snap": sum(snaps) / len(snaps) if snaps else None,
        "n": n,
    }


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


def _snap_threshold_for_stat(stat_type: str, position: Optional[str]) -> float:
    pos = (position or "").upper()
    if stat_type in ("passing_yards", "completions", "attempts", "pass_attempts"):
        return SNAP_MIN_QB
    if stat_type in ("rushing_yards", "rushing_attempts") or pos in ("RB", "FB", "HB"):
        return SNAP_MIN_RB
    if stat_type in ("receptions", "receiving_yards", "targets") or pos in ("WR", "TE"):
        return SNAP_MIN_WR_TE
    if pos == "QB":
        return SNAP_MIN_QB
    if pos in ("RB", "FB", "HB"):
        return SNAP_MIN_RB
    return SNAP_MIN_WR_TE


def _fallback_usage_pass(stat_type: str, usage: dict, position: Optional[str]) -> bool:
    """When snap % is missing, require clear primary usage."""
    pos = (position or "").upper()
    if stat_type in ("passing_yards", "completions", "attempts", "pass_attempts") or pos == "QB":
        return usage.get("pass_attempts", 0) >= 22.0
    if stat_type in ("rushing_yards", "rushing_attempts") or pos in ("RB", "FB", "HB"):
        return usage.get("rush_attempts", 0) >= 10.0
    if stat_type in ("receptions", "receiving_yards", "targets") or pos in ("WR", "TE"):
        return usage.get("targets", 0) >= 5.5 or usage.get("receptions", 0) >= 4.0
    return False


def nfl_player_role_eligible(
    db: Session,
    player_id: int,
    stat_type: str,
    min_games: int = 5,
    lookback_games: int = 8,
    game_id: Optional[int] = None,
) -> Tuple[bool, str]:
    player = db.query(Player).filter(Player.player_id == player_id).first()
    position = player.position if player else None

    game_row = (
        db.query(Game).filter(Game.game_id == game_id).first() if game_id is not None else None
    )

    if game_id is not None:
        from app.services.lineup_service import LineupService

        if LineupService(db).is_player_starter(game_id, player_id):
            return True, "confirmed_starter"

    starter_rate, starter_n = _recent_starter_rate(db, player_id, lookback_games)
    if starter_n >= STARTER_GAMES_MIN and starter_rate >= STARTER_RATE_MIN:
        return True, "depth_chart_starter"

    rows = _recent_game_stats(db, player_id, lookback_games)
    if len(rows) < min_games:
        return False, f"only {len(rows)} recent games (need {min_games})"

    usage = _usage_averages(rows)
    snap_need = _snap_threshold_for_stat(stat_type, position)
    if (
        game_row
        and game_row.game_status == "scheduled"
        and game_id is not None
        and db.query(BettingLine)
        .filter(
            BettingLine.game_id == game_id,
            BettingLine.player_id == player_id,
            BettingLine.stat_type == stat_type,
        )
        .first()
    ):
        snap_need = max(snap_need * 0.88, 36.0)

    avg_snap = usage.get("avg_snap")

    if avg_snap is not None:
        if avg_snap >= snap_need:
            return True, f"snap {avg_snap:.0f}%"
        return False, f"avg snap {avg_snap:.0f}% < {snap_need:.0f}%"

    if _fallback_usage_pass(stat_type, usage, position):
        return True, "primary_usage_no_snap_data"
    if starter_n >= 3 and starter_rate >= 0.65:
        return True, "high_starter_rate_no_snaps"

    return False, "not primary role (snaps/usage/starter)"
