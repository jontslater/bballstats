"""NFL suggested-bet / prop eligibility from recent role and sample size."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple

from sqlalchemy.orm import Session

from app.models import Game, PlayerGameStat


def _game_has_stat_usage(stat: PlayerGameStat, stat_type: str) -> bool:
    if stat_type in ("passing_yards", "completions", "attempts", "pass_attempts"):
        return (stat.pass_attempts or 0) >= 8
    if stat_type in ("rushing_yards", "rushing_attempts"):
        return (stat.rushing_attempts or 0) >= 3
    if stat_type in ("receptions", "receiving_yards", "targets"):
        return (stat.targets or 0) >= 2 or (stat.receptions or 0) >= 2
    if stat_type == "anytime_td":
        return (stat.rushing_attempts or 0) > 0 or (stat.targets or 0) > 0
    return True


def nfl_player_role_eligible(
    db: Session,
    player_id: int,
    stat_type: str,
    min_games: int = 5,
    min_snap_pct: float = 25.0,
    lookback_games: int = 8,
) -> Tuple[bool, str]:
    """Require enough recent games with meaningful usage for this stat type."""
    cutoff = date.today() - timedelta(days=200)
    rows = (
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
    if len(rows) < min_games:
        return False, f"only {len(rows)} recent games (need {min_games})"

    active_games = sum(1 for stat, _ in rows if _game_has_stat_usage(stat, stat_type))
    min_active = max(3, min_games - 1)
    if active_games < min_active:
        return False, f"only {active_games} games with role usage for {stat_type}"

    snap_pcts = [float(s.snap_percentage) for s, _ in rows if s.snap_percentage and s.snap_percentage > 0]
    if snap_pcts:
        avg_snap = sum(snap_pcts) / len(snap_pcts)
        if avg_snap < min_snap_pct:
            return False, f"avg snap {avg_snap:.0f}% < {min_snap_pct}%"

    return True, "ok"
