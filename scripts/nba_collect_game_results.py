#!/usr/bin/env python3
"""
Collect NBA finals and box scores from ESPN summary API.

Usage:
    python scripts/nba_collect_game_results.py --previous-day
    python scripts/nba_collect_game_results.py --lookback-days 7
    python scripts/nba_collect_game_results.py --start-date 2025-10-21 --end-date 2026-04-13
    python scripts/nba_collect_game_results.py --season 2025-26 --skip-existing
"""
import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.models import Season
from app.scrapers.espn_nba_client import ESPNNBAClient
from app.services.nba_results import NBA_RESULTS_LOOKBACK_DAYS, collect_games_for_date


def backfill_range(db, client, start: date, end: date, skip_existing: bool = False):
    total_created = total_processed = 0
    days = (end - start).days + 1
    current = start
    day_num = 0
    while current <= end:
        day_num += 1
        created, processed = collect_games_for_date(db, client, current, skip_if_has_stats=skip_existing)
        total_created += created
        total_processed += processed
        if processed or created:
            print(f"  [{day_num}/{days}] {current}: created={created}, processed={processed}")
        db.commit()
        current += timedelta(days=1)
        if current <= end:
            time.sleep(0.2)
    print(f"SUMMARY: created={total_created}, processed={total_processed}")


def main():
    parser = argparse.ArgumentParser(description="Collect NBA game results from ESPN")
    parser.add_argument("--date", type=str)
    parser.add_argument("--previous-day", action="store_true")
    parser.add_argument("--lookback-days", type=int, nargs="?", const=NBA_RESULTS_LOOKBACK_DAYS)
    parser.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)
    parser.add_argument("--season", type=str)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    client = ESPNNBAClient(delay=0.35)
    try:
        if args.previous_day or args.date:
            d = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
            c, p = collect_games_for_date(db, client, d, skip_if_has_stats=args.skip_existing)
            db.commit()
            print(f"Date {d}: created={c}, processed={p}")
            return 0

        if args.lookback_days is not None and not (args.start_date or args.end_date):
            end = date.today()
            start = end - timedelta(days=args.lookback_days)
            backfill_range(db, client, start, end, skip_existing=args.skip_existing)
            return 0

        start = date.fromisoformat(args.start_date) if args.start_date else None
        end = date.fromisoformat(args.end_date) if args.end_date else date.today() - timedelta(days=1)
        if args.season:
            season = db.query(Season).filter(Season.sport == "NBA", Season.season_year == args.season).first()
            if season:
                start = start or season.start_date
                end = end or min(season.end_date or date.today(), date.today())
        if not start:
            start = end - timedelta(days=90)
        backfill_range(db, client, start, end, skip_existing=args.skip_existing)
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
