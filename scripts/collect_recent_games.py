#!/usr/bin/env python3
"""
Collect recent games (last 30 days) for analytics testing.

Usage:
    python scripts/collect_recent_games.py [--days 30]
"""
import sys
from pathlib import Path
from datetime import date, timedelta

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from scripts.collect_game_results import collect_previous_day_games

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Collect recent games for analytics')
    parser.add_argument('--days', type=int, default=30, help='Number of days to collect (default: 30)')
    
    args = parser.parse_args()
    
    print("🏀 Collecting Recent Games for Analytics...")
    print("=" * 60)
    print(f"Collecting games from the last {args.days} days...")
    print("This will take a while due to rate limiting...")
    print("=" * 60)
    print()
    
    end_date = date.today() - timedelta(days=1)  # Yesterday (most recent finished games)
    start_date = end_date - timedelta(days=args.days - 1)
    
    current_date = start_date
    total_games = 0
    
    while current_date <= end_date:
        print(f"\n📅 Processing {current_date}...")
        try:
            collect_previous_day_games(current_date)
            total_games += 1
        except Exception as e:
            print(f"  ⚠️  Error: {e}")
        
        current_date += timedelta(days=1)
        
        # Small delay between days
        if current_date <= end_date:
            import time
            time.sleep(2)
    
    print("\n" + "=" * 60)
    print(f"✅ Completed! Processed {args.days} days of games")
    print("=" * 60)





