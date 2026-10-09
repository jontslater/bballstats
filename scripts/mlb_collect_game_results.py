#!/usr/bin/env python3
"""
Collect MLB game results and box scores from MLB Stats API.

Uses official MLB Stats API - no rate limits (unlike Baseball Reference).
Matches existing Game rows by espn_game_id='MLB_<gamePk>' first (schedule persist
key), then date+teams. Lookback backfills missed finals, not only previous-day.

Usage:
    python scripts/mlb_collect_game_results.py [--date DATE]
    python scripts/mlb_collect_game_results.py --previous-day
    python scripts/mlb_collect_game_results.py --lookback-days 7
    python scripts/mlb_collect_game_results.py --season 2025 --days 90
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime, date, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.scrapers.mlb_api_client import MLBAPIClient
from app.services.mlb_results import (
    MLB_RESULTS_LOOKBACK_DAYS,
    collect_games_for_date,
)


def collect_season_games(
    season_year: str = None,
    start_date: date = None,
    end_date: date = None,
    days_back: int = None,
    skip_existing: bool = False
):
    """Collect MLB game results for a date range. Uses MLB API - fast, no rate limits."""
    print("⚾ Collecting MLB Historical Game Results (MLB Stats API)...")
    print("=" * 60)

    db = SessionLocal()
    client = MLBAPIClient(delay=0.3)

    try:
        from app.models import Season
        season = None
        if season_year:
            season = db.query(Season).filter(
                Season.sport == 'MLB',
                Season.season_year == str(season_year)
            ).first()

        if season and not start_date:
            start_date = season.start_date
        # If season has no start_date (seed doesn't set it), use MLB calendar defaults
        if not start_date and season_year:
            y = int(season_year)
            start_date = date(y, 3, 15)  # Spring training / opening day
        if not start_date:
            start_date = date.today() - timedelta(days=90)

        if end_date is None:
            if days_back:
                end_date = date.today() - timedelta(days=1)
                start_date = end_date - timedelta(days=days_back)
            else:
                # Use season end_date if set, else MLB default (Oct 31) or yesterday
                if season and season.end_date:
                    end_date = season.end_date
                elif season_year:
                    y = int(season_year)
                    end_date = date(y, 10, 31)  # Regular season + playoffs
                else:
                    end_date = date.today() - timedelta(days=1)

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        total_days = (end_date - start_date).days + 1
        print(f"Date range: {start_date} to {end_date} ({total_days} days)")
        if skip_existing:
            print("Skipping dates that already have stats")
        print()

        total_created = total_processed = 0
        current = start_date
        day_num = 0

        while current <= end_date:
            day_num += 1
            c, p = collect_games_for_date(db, client, current, skip_if_has_stats=skip_existing)
            total_created += c
            total_processed += p
            if p > 0 or c > 0:
                print(f"  [{day_num}/{total_days}] {current}: {c} created, {p} processed")

            current += timedelta(days=1)

        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"✅ Games created: {total_created}")
        print(f"✅ Games processed: {total_processed}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description='Collect MLB game results from MLB Stats API')
    parser.add_argument('--date', type=str, help='Single date YYYY-MM-DD')
    parser.add_argument('--previous-day', action='store_true')
    parser.add_argument(
        '--lookback-days',
        type=int,
        nargs='?',
        const=MLB_RESULTS_LOOKBACK_DAYS,
        help=f'Backfill finals from N days ago through today (default {MLB_RESULTS_LOOKBACK_DAYS} if flag given with no value)',
    )
    parser.add_argument('--season', type=str, help='Season year (e.g., 2025)')
    parser.add_argument('--start-date', type=str, help='Start date YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, help='End date YYYY-MM-DD')
    parser.add_argument('--days', type=int, help='Number of days to collect')
    parser.add_argument('--skip-existing', action='store_true', help='Skip dates with stats')
    args = parser.parse_args()

    if args.lookback_days is not None and not (args.start_date or args.end_date or args.date or args.previous_day):
        end = date.today()
        start = end - timedelta(days=args.lookback_days)
        collect_season_games(start_date=start, end_date=end, skip_existing=args.skip_existing)
        return

    if args.previous_day:
        game_date = date.today() - timedelta(days=1)
        db = SessionLocal()
        client = MLBAPIClient(delay=0.3)
        try:
            c, p = collect_games_for_date(db, client, game_date)
            print(f"Created {c} games, processed {p} games")
        finally:
            db.close()
        return

    if args.date and not (args.start_date or args.end_date or args.days):
        game_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        db = SessionLocal()
        client = MLBAPIClient(delay=0.3)
        try:
            c, p = collect_games_for_date(db, client, game_date)
            print(f"Created {c} games, processed {p} games")
        finally:
            db.close()
        return

    start = datetime.strptime(args.start_date, '%Y-%m-%d').date() if args.start_date else None
    end = datetime.strptime(args.end_date, '%Y-%m-%d').date() if args.end_date else None

    collect_season_games(
        season_year=args.season,
        start_date=start,
        end_date=end,
        days_back=args.days,
        skip_existing=args.skip_existing
    )


if __name__ == "__main__":
    main()
