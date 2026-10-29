"""
Blend current- and prior-season NBA samples for early-season predictions.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Game, PlayerGameStat, Season
from app.services.distribution_engine import DistributionEngine

NBA_BLEND_MIN_CURRENT_GAMES = 10


def prior_nba_season_id(db: Session, current_season_id: int) -> Optional[int]:
    season = db.query(Season).filter(Season.season_id == current_season_id).first()
    if not season or season.sport != "NBA":
        return None
    try:
        start_year = int(str(season.season_year).split("-")[0])
    except (ValueError, IndexError):
        return None
    prev = (
        db.query(Season)
        .filter(Season.sport == "NBA", Season.season_year.like(f"{start_year - 1}%"))
        .order_by(Season.season_id.desc())
        .first()
    )
    return prev.season_id if prev else None


def count_finished_games(
    db: Session,
    player_id: int,
    season_id: int,
    *,
    as_of_date: Optional[date] = None,
) -> int:
    q = (
        db.query(func.count(PlayerGameStat.stat_id))
        .join(Game, Game.game_id == PlayerGameStat.game_id)
        .filter(
            PlayerGameStat.sport == "NBA",
            PlayerGameStat.player_id == player_id,
            Game.season_id == season_id,
            Game.game_status == "finished",
            PlayerGameStat.minutes_played > 0,
        )
    )
    if as_of_date is not None:
        q = q.filter(Game.game_date < as_of_date)
    return q.scalar() or 0


def _blend_stats(
    current: Optional[Dict[str, Any]],
    prior: Optional[Dict[str, Any]],
    n_current: int,
    min_current: int = NBA_BLEND_MIN_CURRENT_GAMES,
) -> Optional[Dict[str, Any]]:
    if n_current >= min_current and current:
        return current
    if not current and not prior:
        return None
    if not prior:
        return current
    if not current or n_current == 0:
        return prior
    w = min(1.0, n_current / float(min_current))
    mean = w * current["mean"] + (1.0 - w) * prior["mean"]
    std_c = current.get("std_dev") or 1.0
    std_p = prior.get("std_dev") or 1.0
    std = math.sqrt(max(w * std_c**2 + (1.0 - w) * std_p**2, 1e-6))
    blended = dict(current)
    blended["mean"] = round(mean, 2)
    blended["std_dev"] = round(std, 2)
    blended["sample_size"] = n_current + int(prior.get("sample_size", 0) * (1.0 - w))
    blended["blend_weight_current"] = round(w, 3)
    return blended


def blended_nba_base_distribution(
    dist_engine: DistributionEngine,
    db: Session,
    player_id: int,
    stat_type: str,
    projected_minutes: float,
    current_season_id: int,
    min_games: int = NBA_BLEND_MIN_CURRENT_GAMES,
    *,
    as_of_date: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    n_current = count_finished_games(
        db, player_id, current_season_id, as_of_date=as_of_date
    )
    current = dist_engine.calculate_base_distribution(
        player_id=player_id,
        stat_type=stat_type,
        sport="NBA",
        projected_minutes=projected_minutes,
        season_ids=[current_season_id],
        min_games=1,
        as_of_date=as_of_date,
    )
    if n_current >= min_games:
        full = dist_engine.calculate_base_distribution(
            player_id=player_id,
            stat_type=stat_type,
            sport="NBA",
            projected_minutes=projected_minutes,
            season_ids=[current_season_id],
            min_games=min_games,
            as_of_date=as_of_date,
        )
        if full:
            full["blend_weight_current"] = 1.0
        return full

    prior_id = prior_nba_season_id(db, current_season_id)
    prior = None
    if prior_id:
        prior = dist_engine.calculate_base_distribution(
            player_id=player_id,
            stat_type=stat_type,
            sport="NBA",
            projected_minutes=projected_minutes,
            season_ids=[prior_id],
            min_games=min_games,
            as_of_date=as_of_date,
        )
    return _blend_stats(current, prior, n_current, min_games)


def blended_nba_avg_minutes(
    dist_engine: DistributionEngine,
    db: Session,
    player_id: int,
    current_season_id: int,
    recent_games: int = 10,
    only_starters: bool = False,
    min_games: int = NBA_BLEND_MIN_CURRENT_GAMES,
    *,
    as_of_date: Optional[date] = None,
) -> Optional[float]:
    n_current = count_finished_games(
        db, player_id, current_season_id, as_of_date=as_of_date
    )
    current = dist_engine.get_historical_avg_minutes(
        player_id,
        sport="NBA",
        season_ids=[current_season_id],
        recent_games=recent_games,
        only_starters=only_starters,
        as_of_date=as_of_date,
    )
    if n_current >= min_games and current:
        return current

    prior_id = prior_nba_season_id(db, current_season_id)
    prior = None
    if prior_id:
        prior = dist_engine.get_historical_avg_minutes(
            player_id,
            sport="NBA",
            season_ids=[prior_id],
            recent_games=recent_games,
            only_starters=only_starters,
            as_of_date=as_of_date,
        )
    if current is None and prior is None:
        return None
    if prior is None:
        return current
    if current is None or n_current == 0:
        return prior
    w = min(1.0, n_current / float(min_games))
    return w * current + (1.0 - w) * prior


def nba_rate_scaled_mean(
    base_mean: float,
    historical_avg_minutes: float,
    projected_minutes: float,
    *,
    max_minutes_ratio: float = 1.05,
) -> float:
    """Scale per-game mean to projected minutes using per-minute rate from sample minutes."""
    if historical_avg_minutes <= 0 or projected_minutes <= 0:
        return base_mean
    capped_projected = min(projected_minutes, historical_avg_minutes * max_minutes_ratio)
    rate = base_mean / historical_avg_minutes
    return round(rate * capped_projected, 2)


def nba_context_multiplier_cap(factors: List[float], cap: float = 1.05) -> float:
    product = 1.0
    for f in factors:
        product *= f if f is not None else 1.0
    if product <= cap:
        return product
    return cap
