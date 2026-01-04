#!/usr/bin/env python3
"""
Generate predictions for historical/finished games.

This allows us to build historical data for analysis even if we didn't
generate predictions before those games were played.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.prediction_service import PredictionService
from app.models import Game
from datetime import date, timedelta
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate predictions for historical games')
    parser.add_argument('--days', type=int, default=30, help='Generate for last N days of finished games (default: 30)')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--stat-types', type=str, default='points,rebounds,assists',
                       help='Comma-separated stat types (default: points,rebounds,assists)')
    
    args = parser.parse_args()
    
    print("📊 Generating Historical Predictions...")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        service = PredictionService(db)
        
        stat_types = [s.strip() for s in args.stat_types.split(',')]
        
        # Determine date range
        if args.start_date and args.end_date:
            start_date = date.fromisoformat(args.start_date)
            end_date = date.fromisoformat(args.end_date)
        else:
            end_date = date.today() - timedelta(days=1)  # Yesterday (most recent finished games)
            start_date = end_date - timedelta(days=args.days)
        
        print(f"Date range: {start_date} to {end_date}")
        
        # Get finished games in date range
        games = db.query(Game).filter(
            Game.game_date >= start_date,
            Game.game_date <= end_date,
            Game.game_status == 'finished'
        ).order_by(Game.game_date.desc()).all()
        
        print(f"Found {len(games)} finished games")
        
        if len(games) == 0:
            print("No finished games found in date range")
            sys.exit(0)
        
        total_created = 0
        total_updated = 0
        total_skipped = 0
        
        for idx, game in enumerate(games, 1):
            print(f"\nProcessing game {idx}/{len(games)}: {game.game_date} (Game {game.game_id})...")
            
            try:
                results = service.generate_predictions_for_game(game.game_id, stat_types)
                total_created += results['created']
                total_updated += results['updated']
                total_skipped += results.get('skipped', 0)
                
                print(f"  Created: {results['created']}, Updated: {results['updated']}, Skipped: {results.get('skipped', 0)}")
            except Exception as e:
                print(f"  ⚠️  Error: {e}")
                total_skipped += 1
                continue
        
        print("\n" + "=" * 60)
        print(f"✅ Complete!")
        print(f"   Total Created: {total_created}")
        print(f"   Total Updated: {total_updated}")
        print(f"   Total Skipped: {total_skipped}")
        print(f"\n💡 Next step: Run evaluation script to check which predictions hit:")
        print(f"   python scripts/evaluate_predictions.py --start-date {start_date} --end-date {end_date}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

