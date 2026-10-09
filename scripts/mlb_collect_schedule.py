#!/usr/bin/env python3
"""
Collect and store MLB game schedules from MLB Stats API.

Uses official MLB Stats API - no rate limits (unlike Baseball Reference).
Persists both GameSchedule and Game rows (espn_game_id='MLB_<gamePk>') so
predictions and suggested bets can see upcoming regular-season and postseason games.

Reconciles a lookback window: games the Stats API no longer lists (dropped
if-necessary / series-clinched) or lists as Unknown/Cancelled/Postponed are
marked cancelled. Finished games with scores are never deleted.

Usage:
    python scripts/mlb_collect_schedule.py [--season SEASON] [--start-date DATE] [--end-date DATE]
    python scripts/mlb_collect_schedule.py --days 7  # Collect next 7 days plus lookback
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
from app.services.mlb_schedule import (
    MLB_SCHEDULE_LOOKBACK_DAYS,
    persist_mlb_schedule_games,
    reconcile_mlb_schedule_window,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=str, help='Season year (e.g., 2024)')
    parser.add_argument('--start-date', type=str, help='Start date YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, help='End date YYYY-MM-DD')
    parser.add_argument('--days', type=int, default=30, help='Number of days ahead to collect (from today)')
    parser.add_argument(
        '--lookback-days',
        type=int,
        default=MLB_SCHEDULE_LOOKBACK_DAYS,
        help=f'Days before today to re-sync and cancel dropped games (default {MLB_SCHEDULE_LOOKBACK_DAYS})',
    )
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

        today = date.today()
        if args.start_date:
            start = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        else:
            start = today - timedelta(days=max(0, args.lookback_days))
        if args.end_date:
            end = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        elif args.start_date:
            end = start + timedelta(days=args.days)
        else:
            end = today + timedelta(days=args.days)

        if start > end:
            start, end = end, start

        print(f"Collecting MLB schedule from {start} to {end} (MLB Stats API)...")
        try:
            games = client.get_schedule(start_date=start, end_date=end)
        except Exception as e:
            print(f"Schedule fetch failed; skipping persist/reconcile so games are not voided: {e}")
            return 1

        result = persist_mlb_schedule_games(db, games, season)
        rec = reconcile_mlb_schedule_window(db, games, start, end)
        db.commit()

        print(
            f"Games created: {result['created_games']}, updated: {result['updated_games']}; "
            f"Schedules created: {result['created_schedules']}, updated: {result['updated_schedules']}; "
            f"Cancelled (dropped/unplayable): games={rec['cancelled_games']}, "
            f"schedules={rec['cancelled_schedules']}; "
            f"Errors: {result['errors']}, skipped (non-R/postseason): {result['skipped_type']}"
        )
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
