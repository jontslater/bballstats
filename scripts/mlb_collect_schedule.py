#!/usr/bin/env python3
"""
Collect and store MLB game schedules from MLB Stats API.

Uses official MLB Stats API - no rate limits (unlike Baseball Reference).
Persists both GameSchedule and Game rows (espn_game_id='MLB_<gamePk>') so
predictions and suggested bets can see upcoming regular-season and postseason games.

Usage:
    python scripts/mlb_collect_schedule.py [--season SEASON] [--start-date DATE] [--end-date DATE]
    python scripts/mlb_collect_schedule.py --days 7  # Collect next 7 days
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime, date, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.models import Season
from app.scrapers.mlb_api_client import MLBAPIClient
from app.services.mlb_schedule import persist_mlb_schedule_games


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=str, help='Season year (e.g., 2024)')
    parser.add_argument('--start-date', type=str, help='Start date YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, help='End date YYYY-MM-DD')
    parser.add_argument('--days', type=int, default=30, help='Number of days to collect')
    args = parser.parse_args()

    db = SessionLocal()
    client = MLBAPIClient(delay=0.5)

    try:
        season_year = args.season or str(date.today().year)
        season = db.query(Season).filter(
            Season.sport == 'MLB',
            Season.season_year == season_year
        ).first()
        if not season:
            print(f"Season {season_year} not found. Run seed_mlb_teams.py first.")
            return 1

        if args.start_date:
            start = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        else:
            start = date.today()
        if args.end_date:
            end = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        else:
            end = start + timedelta(days=args.days)

        print(f"Collecting MLB schedule from {start} to {end} (MLB Stats API)...")
        totals = {
            'created_schedules': 0,
            'updated_schedules': 0,
            'created_games': 0,
            'updated_games': 0,
            'errors': 0,
            'skipped_type': 0,
        }

        current = start
        while current <= end:
            games = client.get_schedule(game_date=current)
            result = persist_mlb_schedule_games(db, games, season)
            for key in totals:
                totals[key] += result.get(key, 0)
            db.commit()
            current += timedelta(days=1)

        print(
            f"Games created: {totals['created_games']}, updated: {totals['updated_games']}; "
            f"Schedules created: {totals['created_schedules']}, updated: {totals['updated_schedules']}; "
            f"Errors: {totals['errors']}, skipped (non-R/postseason): {totals['skipped_type']}"
        )
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
