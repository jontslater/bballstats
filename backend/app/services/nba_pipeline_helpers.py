"""Helpers for NBA update pipeline validation."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple

from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.prediction import Prediction


def nba_prediction_generation_ok(
    db: Session,
    *,
    days_ahead: int = 1,
    created: int = 0,
    updated: int = 0,
) -> Tuple[bool, str]:
    """
    Fail when scheduled/in-progress NBA games in the window have zero predictions
    after a generation run that reported no creates/updates.
    """
    today = date.today()
    end = today + timedelta(days=days_ahead)
    games = (
        db.query(Game)
        .filter(
            Game.sport == "NBA",
            Game.game_date >= today,
            Game.game_date <= end,
            Game.game_status.in_(("scheduled", "in_progress")),
        )
        .all()
    )
    if not games:
        return True, "no upcoming NBA games in window"

    if created + updated > 0:
        return True, f"created={created} updated={updated}"

    for game in games:
        n = (
            db.query(Prediction)
            .filter(
                Prediction.sport == "NBA",
                Prediction.game_id == game.game_id,
                Prediction.bet_type != "pass",
            )
            .count()
        )
        if n == 0:
            return False, f"game_id={game.game_id} on {game.game_date} has 0 predictions"
    return True, "predictions present for all upcoming games"
