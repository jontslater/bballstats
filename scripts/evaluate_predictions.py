#!/usr/bin/env python3
"""
Evaluate predictions for finished games.

This script checks which predictions hit after games finish.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.prediction_evaluator import PredictionEvaluator
from datetime import date, timedelta
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Evaluate predictions for finished games')
    parser.add_argument('--date', type=str, help='Evaluate specific date (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=7, help='Evaluate last N days (default: 7)')
    parser.add_argument('--game-id', type=int, help='Evaluate specific game')
    
    args = parser.parse_args()
    
    print("📊 Evaluating Predictions...")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        evaluator = PredictionEvaluator(db)
        
        if args.game_id:
            print(f"Evaluating predictions for game {args.game_id}...")
            result = evaluator.evaluate_game(args.game_id)
            print(f"✅ Evaluated: {result['evaluated']}")
            print(f"   Skipped: {result['skipped']}")
            if result['errors'] > 0:
                print(f"   Errors: {result['errors']}")
        
        elif args.date:
            try:
                target_date = date.fromisoformat(args.date)
                print(f"Evaluating predictions for {target_date}...")
                result = evaluator.evaluate_date(target_date)
                print(f"✅ Games processed: {result['games_processed']}")
                print(f"   Evaluated: {result['evaluated']}")
                print(f"   Skipped: {result['skipped']}")
                if result['errors'] > 0:
                    print(f"   Errors: {result['errors']}")
            except ValueError:
                print(f"❌ Invalid date format: {args.date}")
                print("   Use YYYY-MM-DD format")
        
        else:
            # Evaluate last N days
            end_date = date.today()
            start_date = end_date - timedelta(days=args.days)
            
            print(f"Evaluating predictions from {start_date} to {end_date}...")
            
            total_games = 0
            total_evaluated = 0
            total_skipped = 0
            total_errors = 0
            
            current_date = start_date
            while current_date <= end_date:
                result = evaluator.evaluate_date(current_date)
                total_games += result['games_processed']
                total_evaluated += result['evaluated']
                total_skipped += result['skipped']
                total_errors += result['errors']
                current_date += timedelta(days=1)
            
            print(f"✅ Games processed: {total_games}")
            print(f"   Evaluated: {total_evaluated}")
            print(f"   Skipped: {total_skipped}")
            if total_errors > 0:
                print(f"   Errors: {total_errors}")
        
        print("=" * 60)
        print("✅ Complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


