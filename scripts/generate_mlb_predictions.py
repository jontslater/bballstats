#!/usr/bin/env python3
"""
Generate MLB predictions for upcoming games.

Usage:
    python scripts/generate_mlb_predictions.py [--date DATE] [--game-id GAME_ID]
"""
import sys
import argparse
from pathlib import Path
from datetime import date, datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Game, Player, PlayerGameStat
from app.services.prediction_service import PredictionService
from app.config.sport_config import get_sport_config


BATTER_POSITIONS = {'C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF', 'DH'}
PITCHER_POSITIONS = {'P', 'SP', 'RP'}
BATTER_STATS = ['hits', 'home_runs', 'total_bases']
PITCHER_STATS = ['strikeouts']


def generate_predictions_for_game(db: Session, game_id: int):
    game = db.query(Game).filter(Game.game_id == game_id).first()
    if not game:
        print(f"Game {game_id} not found")
        return
    if game.sport != 'MLB':
        print(f"Game {game_id} is not MLB")
        return

    print(f"\nGenerating MLB predictions for Game {game_id}")
    print(f"   {game.away_team.name} @ {game.home_team.name} on {game.game_date}")
    print("=" * 60)

    pred_service = PredictionService(db, sport='MLB')

    players_with_stats = db.query(PlayerGameStat.player_id).filter(
        PlayerGameStat.sport == 'MLB',
        PlayerGameStat.team_id.in_([game.home_team_id, game.away_team_id]),
        PlayerGameStat.game_id != game_id
    ).distinct().all()
    player_ids = [p[0] for p in players_with_stats]

    all_players = db.query(Player).filter(
        Player.sport == 'MLB',
        Player.player_id.in_(player_ids)
    ).all()

    if not all_players:
        players_in_game = db.query(Player).filter(
            Player.sport == 'MLB',
            Player.current_team_id.in_([game.home_team_id, game.away_team_id])
        ).all()
        all_players = players_in_game

    print(f"Found {len(all_players)} players")
    created = skipped = 0

    for player in all_players:
        pos = (player.position or '').upper()
        if pos in PITCHER_POSITIONS:
            stat_types = PITCHER_STATS
        elif pos in BATTER_POSITIONS or not pos:
            stat_types = BATTER_STATS
        else:
            stat_types = BATTER_STATS + PITCHER_STATS

        for stat_type in stat_types:
            try:
                pred = pred_service.generate_prediction(
                    player_id=player.player_id,
                    game_id=game_id,
                    stat_type=stat_type
                )
                if pred:
                    line = getattr(pred, 'safe_line', 0) or 0
                    prob = getattr(pred, 'safe_probability', 0) or 0
                    if line < 0:
                        skipped += 1
                        continue
                    created += 1
                    print(f"  {player.name} ({player.position or '?'}) - {stat_type}: {line:.1f} ({prob*100:.0f}%)")
                    db.commit()
                else:
                    skipped += 1
            except Exception as e:
                skipped += 1
                if skipped <= 5:
                    print(f"  Skip {player.name} {stat_type}: {e}")

    print(f"\nCreated: {created}, Skipped: {skipped}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str)
    parser.add_argument('--game-id', type=int)
    parser.add_argument('--upcoming', action='store_true')
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.game_id:
            generate_predictions_for_game(db, args.game_id)
        elif args.date:
            d = datetime.strptime(args.date, '%Y-%m-%d').date()
            games = db.query(Game).filter(
                Game.sport == 'MLB',
                Game.game_date == d,
                Game.game_status.in_(['scheduled', 'in_progress'])
            ).all()
            for g in games:
                generate_predictions_for_game(db, g.game_id)
        elif args.upcoming:
            today = date.today()
            end = today + timedelta(days=7)
            games = db.query(Game).filter(
                Game.sport == 'MLB',
                Game.game_date >= today,
                Game.game_date <= end,
                Game.game_status == 'scheduled'
            ).all()
            for g in games:
                generate_predictions_for_game(db, g.game_id)
        else:
            print("Specify --date, --game-id, or --upcoming")
    finally:
        db.close()


if __name__ == "__main__":
    main()
