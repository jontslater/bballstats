#!/usr/bin/env python3
"""
Collect games from the start of the current NBA season.

Usage:
    python scripts/collect_season_games.py [--start-date 2024-10-22] [--end-date 2024-12-27]
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
    
    parser = argparse.ArgumentParser(description='Collect games from NBA season')
    parser.add_argument('--start-date', type=str, default='2024-10-22', 
                       help='Start date (YYYY-MM-DD). Default: 2024-10-22 (start of 2024-25 season)')
    parser.add_argument('--end-date', type=str, default=None,
                       help='End date (YYYY-MM-DD). Default: yesterday')
    parser.add_argument('--skip-existing', action='store_true',
                       help='Skip dates that already have games in database')
    
    args = parser.parse_args()
    
    # Parse dates
    start_date = date.fromisoformat(args.start_date)
    if args.end_date:
        end_date = date.fromisoformat(args.end_date)
    else:
        end_date = date.today() - timedelta(days=1)  # Yesterday
    
    print("🏀 Collecting NBA Season Games...")
    print("=" * 60)
    print(f"Date range: {start_date} to {end_date}")
    print(f"Total days: {(end_date - start_date).days + 1}")
    print("This will take a while due to rate limiting...")
    print("=" * 60)
    print()
    
    # Check existing games if skip flag is set
    existing_dates = set()
    if args.skip_existing:
        from app.database import SessionLocal
        from app.models.game import Game
        
        db = SessionLocal()
        try:
            existing_games = db.query(Game.game_date).distinct().all()
            existing_dates = {g[0] for g in existing_games}
            print(f"Found {len(existing_dates)} dates with existing games. Will skip these.")
        except Exception as e:
            print(f"⚠️  Could not check existing games: {e}")
        finally:
            db.close()
    
    current_date = start_date
    total_processed = 0
    total_skipped = 0
    total_errors = 0
    
    while current_date <= end_date:
        # Skip if already exists
        if args.skip_existing and current_date in existing_dates:
            print(f"⏭️  Skipping {current_date} (already has games)")
            total_skipped += 1
            current_date += timedelta(days=1)
            continue
        
        print(f"\n📅 Processing {current_date} ({total_processed + 1}/{((end_date - start_date).days + 1)})...")
        try:
            collect_previous_day_games(current_date)
            total_processed += 1
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            break
        except Exception as e:
            print(f"  ❌ Error: {e}")
            total_errors += 1
        
        current_date += timedelta(days=1)
        
        # Rate limiting delay between days
        if current_date <= end_date:
            import time
            time.sleep(2)  # 2 second delay between days
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"✅ Dates processed: {total_processed}")
    if args.skip_existing:
        print(f"⏭️  Dates skipped (existing): {total_skipped}")
    if total_errors > 0:
        print(f"❌ Dates with errors: {total_errors}")
    print("=" * 60)
    
    # Show final stats
    from app.database import SessionLocal
    from app.models.game import Game
    from app.models.player_game_stat import PlayerGameStat
    
    db = SessionLocal()
    try:
        total_games = db.query(Game).count()
        total_stats = db.query(PlayerGameStat).count()
        unique_players = db.query(PlayerGameStat.player_id).distinct().count()
        
        print(f"\n📊 Database Stats:")
        print(f"   Total games: {total_games}")
        print(f"   Total player stats: {total_stats}")
        print(f"   Unique players: {unique_players}")
    except Exception as e:
        print(f"⚠️  Could not get final stats: {e}")
    finally:
        db.close()


