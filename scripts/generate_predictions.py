#!/usr/bin/env python3
"""
Generate predictions for upcoming games.

Usage:
    # Generate for today's games
    python scripts/generate_predictions.py
    
    # Generate for specific game
    python scripts/generate_predictions.py --game-id 123
    
    # Generate for next N days
    python scripts/generate_predictions.py --days 3
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.prediction_service import PredictionService

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate predictions')
    parser.add_argument('--game-id', type=int, help='Generate for specific game')
    parser.add_argument('--days', type=int, default=1, help='Days ahead to generate (default: 1)')
    parser.add_argument('--stat-types', type=str, default='points,rebounds,assists',
                       help='Comma-separated stat types (default: points,rebounds,assists)')
    
    args = parser.parse_args()
    
    print("🎯 Generating Predictions...")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        service = PredictionService(db)
        
        stat_types = [s.strip() for s in args.stat_types.split(',')]
        
        if args.game_id:
            print(f"Generating predictions for game {args.game_id}...")
            results = service.generate_predictions_for_game(args.game_id, stat_types)
            print(f"✅ Created: {results['created']}, Updated: {results['updated']}")
        else:
            print(f"Generating predictions for next {args.days} days...")
            results = service.generate_predictions_for_upcoming_games(args.days, stat_types)
            print(f"✅ Games processed: {results['games_processed']}")
            print(f"   Created: {results['created']}")
            print(f"   Updated: {results['updated']}")
        
        print("=" * 60)
        print("✅ Complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

