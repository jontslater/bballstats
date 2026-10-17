"""
Shared NFL prop probability path for predictions and sportsbook pricing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Game, Player, Prediction, Season
from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.services.nfl_position_priors import role_for_position
from app.services.prediction_service import PredictionService


def nfl_season_ids_for_game(db: Session, game: Game) -> List[int]:
    season_ids = [game.season_id]
    season_row = db.query(Season).filter(Season.season_id == game.season_id).first()
    if season_row:
        try:
            prev_year = str(int(season_row.season_year) - 1)
            prev_season = db.query(Season).filter(
                Season.sport == "NFL",
                Season.season_year == prev_year,
            ).first()
            if prev_season and prev_season.season_id not in season_ids:
                season_ids.append(prev_season.season_id)
        except ValueError:
            pass
    return season_ids


def get_nfl_adjusted_distribution(
    db: Session,
    player_id: int,
    game_id: int,
    stat_type: str,
) -> Optional[Dict[str, Any]]:
    """
    Same adjusted mean/std/sample as generate_prediction (NFL).
    Reuses standard Prediction row when already generated.
    """
    pred = (
        db.query(Prediction)
        .filter(
            Prediction.sport == "NFL",
            Prediction.player_id == player_id,
            Prediction.game_id == game_id,
            Prediction.stat_type == stat_type,
            Prediction.bet_type == "standard",
        )
        .first()
    )
    if pred and pred.distribution_mean is not None and pred.distribution_std_dev is not None:
        player = db.query(Player).filter(Player.player_id == player_id).first()
        game = db.query(Game).filter(Game.game_id == game_id).first()
        return {
            "adjusted_mean": float(pred.distribution_mean),
            "adjusted_std": float(pred.distribution_std_dev),
            "sample_size": int(pred.sample_size or 5),
            "player": player,
            "game": game,
            "player_role": role_for_position(player.position if player else None),
        }

    svc = PredictionService(db, sport="NFL")
    return svc.build_nfl_prop_distribution(player_id, game_id, stat_type)


def compute_nfl_line_probabilities(
    db: Session,
    player_id: int,
    game_id: int,
    stat_type: str,
    line: float,
    apply_posthoc: bool = True,
) -> Optional[Dict[str, float]]:
    ctx = get_nfl_adjusted_distribution(db, player_id, game_id, stat_type)
    if not ctx:
        return None
    player = ctx.get("player")
    svc = PredictionService(db, sport="NFL")
    league_mean, league_std = svc._get_league_averages(
        stat_type, player_position=player.position if player else None
    )
    calc = CalibratedProbabilityCalculator(sport="NFL")
    modeled = calc.calculate_probability_for_line(
        line=float(line),
        player_mean=ctx["adjusted_mean"],
        player_std=ctx["adjusted_std"],
        sample_size=ctx["sample_size"],
        stat_type=stat_type,
        league_mean=league_mean,
        league_std=league_std,
        player_role=ctx.get("player_role"),
        apply_posthoc=False,
    )
    model_p = modeled["probability"]
    cal_p = model_p
    if apply_posthoc:
        cal_p = calc._get_nfl_posthoc().apply(stat_type, model_p)
    return {
        "model_probability": model_p,
        "calibrated_probability": cal_p,
        "sample_size": ctx["sample_size"],
        "player_mean": ctx["adjusted_mean"],
        "player_std": ctx["adjusted_std"],
    }
