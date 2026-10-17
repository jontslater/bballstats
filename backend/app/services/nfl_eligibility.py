"""NFL suggested-bet / prop eligibility from recent role and sample size."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Game, PlayerGameStat
from app.models.lineup import Lineup


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


def _recent_starter_rate(db: Session, player_id: int, lookback_games: int = 10) -> Tuple[float, int]:
    cutoff = date.today() - timedelta(days=200)
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
        .limit(lookback_games)
        .all()
    )
    if not rows:
        return 0.0, 0
    starters = sum(1 for lineup, _ in rows if lineup.is_starter)
    return starters / len(rows), len(rows)


def nfl_player_role_eligible(
    db: Session,
    player_id: int,
    stat_type: str,
    min_games: int = 5,
    min_snap_pct: float = 40.0,
    lookback_games: int = 8,
    game_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """Require starter depth role, snap share, or confirmed starter for this game."""
    if game_id is not None:
        from app.services.lineup_service import LineupService

        if LineupService(db).is_player_starter(game_id, player_id):
            return True, "confirmed_starter"

    starter_rate, starter_n = _recent_starter_rate(db, player_id, lookback_games=10)
    if starter_n >= 4 and starter_rate >= 0.5:
        pass  # depth-chart starter
    elif starter_n >= 3 and starter_rate >= 0.65:
        pass
    else:
        if starter_n < 3 or starter_rate < 0.4:
            return False, f"starter rate {starter_rate:.0%} over {starter_n} games"

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
    elif starter_rate < 0.55:
        return False, "no snap data and starter rate below 55%"

    return True, "ok"
