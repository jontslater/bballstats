#!/usr/bin/env python3
"""
Generate NFL predictions for upcoming games.

Usage:
    PYTHONUTF8=1 python scripts/generate_nfl_predictions.py --upcoming
    PYTHONUTF8=1 python scripts/generate_nfl_predictions.py --date 2026-10-18
    PYTHONUTF8=1 python scripts/generate_nfl_predictions.py --game-id 123
"""
import sys
import argparse
from pathlib import Path
from datetime import date, datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from typing import List, Optional

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Game, Player, PlayerGameStat
from app.models.prediction import Prediction
from app.services.prediction_service import PredictionService
from app.config.sport_config import get_sport_config, get_bettable_stat_types


def replace_existing_nfl_predictions(db: Session, game_id: int) -> int:
    return db.query(Prediction).filter(
        Prediction.game_id == game_id,
        Prediction.sport == "NFL",
    ).delete(synchronize_session=False)


def stat_types_for_player(position: Optional[str], include_anytime_td: bool = True) -> List[str]:
    config = get_sport_config("NFL")
    defaults = config.get("position_default_stats") or {}
    if position and position in defaults:
        stats = list(defaults[position])
    else:
        stats = [
            s for s in get_bettable_stat_types("NFL")
            if s != "anytime_td"
        ]
    if include_anytime_td and position in ("QB", "RB", "WR", "TE"):
        stats.append("anytime_td")
    # Normalize attempts naming
    return list(dict.fromkeys(stats))


def generate_predictions_for_game(
    db: Session,
    game_id: int,
    pred_service: Optional[PredictionService] = None,
) -> int:
    game = db.query(Game).filter(Game.game_id == game_id).first()
    if not game:
        print(f"Game {game_id} not found")
        return 1
    if game.sport != "NFL":
        print(f"Game {game_id} is not NFL")
        return 1

    print(f"\nGenerating NFL predictions for Game {game_id}")
    print(f"   {game.away_team.name} @ {game.home_team.name} on {game.game_date}")
    print("=" * 60)

    deleted = replace_existing_nfl_predictions(db, game_id)
    if deleted:
        print(f"Replaced {deleted} existing NFL predictions for this game")
        db.commit()

    pred_service = pred_service or PredictionService(db, sport="NFL")

    player_ids = [
        pid for (pid,) in db.query(PlayerGameStat.player_id).join(Game).filter(
            PlayerGameStat.sport == "NFL",
            Game.season_id == game.season_id,
            PlayerGameStat.team_id.in_([game.home_team_id, game.away_team_id]),
            Game.game_id != game.game_id,
        ).distinct().all()
    ]

    players = db.query(Player).filter(
        Player.sport == "NFL",
        Player.player_id.in_(player_ids),
    ).all() if player_ids else []

    if not players:
        players = db.query(Player).filter(
            Player.sport == "NFL",
            Player.current_team_id.in_([game.home_team_id, game.away_team_id]),
        ).all()

    print(f"Found {len(players)} players")
    created = skipped = errors = 0

    for player in players:
        stat_types = stat_types_for_player(player.position)
        for stat_type in stat_types:
            try:
                pred = pred_service.generate_prediction(
                    player_id=player.player_id,
                    game_id=game_id,
                    stat_type=stat_type,
                )
                if pred:
                    line = getattr(pred, "safe_line", 0) or 0
                    if line < 0:
                        skipped += 1
                        continue
                    created += 1
                    db.commit()
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                skipped += 1
                if errors <= 5:
                    print(f"  ERROR: {player.name} {stat_type}: {e}")

    print(f"Created: {created}, Skipped: {skipped}, Errors: {errors}")
    total = created + skipped
    if total > 0 and errors / total > 0.20:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Generate NFL predictions")
    parser.add_argument("--date", type=str)
    parser.add_argument("--game-id", type=int)
    parser.add_argument("--upcoming", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    exit_code = 0
    try:
        pred_service = PredictionService(db, sport="NFL")
        if args.game_id:
            exit_code = generate_predictions_for_game(db, args.game_id, pred_service)
        elif args.date:
            d = datetime.strptime(args.date, "%Y-%m-%d").date()
            games = db.query(Game).filter(
                Game.sport == "NFL",
                Game.game_date == d,
                Game.game_status.in_(["scheduled", "in_progress"]),
            ).all()
            for g in games:
                code = generate_predictions_for_game(db, g.game_id, pred_service)
                exit_code = max(exit_code, code)
        elif args.upcoming:
            today = date.today()
            end = today + timedelta(days=10)
            games = db.query(Game).filter(
                Game.sport == "NFL",
                Game.game_date >= today,
                Game.game_date <= end,
                Game.game_status.in_(["scheduled", "in_progress"]),
            ).all()
            print(f"Upcoming NFL games: {len(games)}")
            for g in games:
                code = generate_predictions_for_game(db, g.game_id, pred_service)
                exit_code = max(exit_code, code)
        else:
            print("Specify --date, --game-id, or --upcoming")
            exit_code = 1
    finally:
        db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
