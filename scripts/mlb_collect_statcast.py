#!/usr/bin/env python3
"""
Ingest Baseball Savant batted-ball data into mlb_statcast_daily.

Daily rows are aggregated per batter and support leak-free walk-forward backtests
(cumulative stats strictly before each game date).

Usage:
    PYTHONPATH=backend python scripts/add_mlb_statcast_schema.py
    PYTHONPATH=backend python scripts/mlb_collect_statcast.py --season 2026 --start-date 2026-03-27 --end-date 2026-04-15
    PYTHONPATH=backend python scripts/mlb_collect_statcast.py --season 2026 --days 7

Season leaderboard CSV (live snapshot only — not for historical backtest):
    PYTHONPATH=backend python scripts/mlb_collect_statcast.py --leaderboard-only --season 2026
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.database import SessionLocal
from app.scrapers.statcast_client import StatcastClient
from app.services.mlb_statcast_service import ingest_statcast_range


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main():
    parser = argparse.ArgumentParser(description="Ingest MLB Statcast batted-ball rollups")
    parser.add_argument("--season", type=int, default=date.today().year)
    parser.add_argument("--start-date", type=parse_date)
    parser.add_argument("--end-date", type=parse_date)
    parser.add_argument("--days", type=int, help="Backfill last N days through today")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument(
        "--leaderboard-only",
        action="store_true",
        help="Fetch season expected-stats CSV (for inspection; not stored yet)",
    )
    args = parser.parse_args()

    if args.leaderboard_only:
        client = StatcastClient()
        csv_text = client.fetch_expected_stats_leaderboard_csv(args.season)
        print(csv_text[:2000])
        print("...")
        print(
            "NOTE: Leaderboard CSV is season-to-date. Backtests should use daily "
            "mlb_statcast_daily rows (--start-date/--end-date) to avoid lookahead."
        )
        return

    end = args.end_date or date.today()
    if args.start_date:
        start = args.start_date
    elif args.days:
        start = end - timedelta(days=args.days - 1)
    else:
        start = end - timedelta(days=6)

    db = SessionLocal()
    try:
        stats = ingest_statcast_range(
            db,
            start_date=start,
            end_date=end,
            season=args.season,
            skip_existing=args.skip_existing,
        )
        print(
            f"Statcast ingest complete: days={stats['days']} rows={stats['rows']} "
            f"skipped={stats['skipped']} ({start} to {end})"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
