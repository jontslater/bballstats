#!/usr/bin/env python3
"""
Script to evaluate all predictions for finished games.

This script finds all finished games with predictions that haven't been evaluated
and evaluates them automatically.
"""
import sys
import os
from datetime import date, timedelta

# Add the backend directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.database import SessionLocal
from app.services.prediction_evaluator import PredictionEvaluator
from app.models.prediction import Prediction
from app.models.game import Game
from sqlalchemy import and_, func, distinct


def evaluate_all_finished_games(days_back: int = 90):
    """
    Evaluate all predictions for finished games.
    
    Args:
        days_back: Number of days back to look for finished games (default: 90)
    """
    db = SessionLocal()
    try:
        print(f"[{date.today()}] Starting evaluation of all finished games...")
        print(f"[{date.today()}] Looking back {days_back} days...")
        
        cutoff_date = date.today() - timedelta(days=days_back)
        
        # Find all finished games with unevaluated predictions
        finished_games = db.query(distinct(Game.game_id), Game.game_date).join(
            Prediction, Game.game_id == Prediction.game_id
        ).filter(
            and_(
                Game.game_status == 'finished',
                Game.game_date >= cutoff_date,
                Prediction.actual_result.is_(None),
                Prediction.bet_type != 'pass'  # Only evaluate non-pass predictions
            )
        ).order_by(Game.game_date.desc()).all()
        
        if not finished_games:
            print(f"[{date.today()}] ✅ No finished games with unevaluated predictions found!")
            return
        
        print(f"[{date.today()}] Found {len(finished_games)} games with unevaluated predictions")
        
        evaluator = PredictionEvaluator(db)
        
        total_evaluated = 0
        total_skipped = 0
        total_errors = 0
        games_processed = 0
        
        for idx, (game_id, game_date) in enumerate(finished_games, 1):
            try:
                print(f"[{date.today()}] Processing game {game_id} ({game_date}) [{idx}/{len(finished_games)}]...", end=' ')
                result = evaluator.evaluate_game(game_id)
                total_evaluated += result['evaluated']
                total_skipped += result['skipped']
                total_errors += result['errors']
                games_processed += 1
                print(f"✅ Evaluated: {result['evaluated']}, Skipped: {result['skipped']}, Errors: {result['errors']}")
            except Exception as e:
                print(f"❌ Error: {e}")
                total_errors += 1
        
        print(f"\n[{date.today()}] ✅ Evaluation complete!")
        print(f"[{date.today()}] Games processed: {games_processed}")
        print(f"[{date.today()}] Total predictions evaluated: {total_evaluated}")
        print(f"[{date.today()}] Total predictions skipped: {total_skipped}")
        print(f"[{date.today()}] Total errors: {total_errors}")
        
    except Exception as e:
        print(f"[{date.today()}] ❌ An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Evaluate all predictions for finished games')
    parser.add_argument(
        '--days-back',
        type=int,
        default=90,
        help='Number of days back to look for finished games (default: 90)'
    )
    
    args = parser.parse_args()
    evaluate_all_finished_games(days_back=args.days_back)


