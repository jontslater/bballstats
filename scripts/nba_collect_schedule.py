#!/usr/bin/env python3
"""
Collect NBA schedules from ESPN (primary).

Usage:
    python scripts/nba_collect_schedule.py --days 30 --lookback-days 7
    python scripts/nba_collect_schedule.py --start-date 2025-10-21 --end-date 2026-04-13
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.models import Season
from app.scrapers.espn_nba_client import ESPNNBAClient
from app.services.nba_schedule import (
    NBA_SCHEDULE_LOOKBACK_DAYS,
    collect_schedule_range,
    persist_nba_schedule_games,
    reconcile_nba_schedule_window,
    resolve_nba_season_for_date,
)


def main():
    parser = argparse.ArgumentParser(description="Collect NBA schedule from ESPN")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--lookback-days", type=int, default=NBA_SCHEDULE_LOOKBACK_DAYS)
    parser.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)
    parser.add_argument("--season", type=str, help="Season year e.g. 2025-26")
    args = parser.parse_args()

    db = SessionLocal()
    client = ESPNNBAClient(delay=0.35)
    try:
        today = date.today()
        if args.start_date:
            start = date.fromisoformat(args.start_date)
        else:
            start = today - timedelta(days=max(0, args.lookback_days))
        if args.end_date:
            end = date.fromisoformat(args.end_date)
        else:
            end = today + timedelta(days=args.days)
        if start > end:
            start, end = end, start

        season = None
        if args.season:
            season = db.query(Season).filter(Season.sport == "NBA", Season.season_year == args.season).first()
        if not season:
            season = resolve_nba_season_for_date(db, start)
        if not season:
            print("No NBA season found. Run scripts/seed_seasons.py")
            return 1

        print(f"Collecting NBA schedule {start} to {end} (ESPN)...")
        all_games = []
        current = start
        totals = {"created_games": 0, "updated_games": 0, "created_schedules": 0, "updated_schedules": 0, "errors": 0}
        while current <= end:
            day_games = client.get_games_for_date(current)
            for g in day_games:
                g["game_date"] = current
            all_games.extend(day_games)
            day_season = resolve_nba_season_for_date(db, current) or season
            if day_games:
                result = persist_nba_schedule_games(db, day_games, day_season)
                for k in totals:
                    totals[k] += result.get(k, 0)
            current += timedelta(days=1)

        rec = reconcile_nba_schedule_window(db, all_games, start, end)
        db.commit()
        print(
            f"Games created={totals['created_games']} updated={totals['updated_games']}; "
            f"schedules created={totals['created_schedules']} updated={totals['updated_schedules']}; "
            f"cancelled games={rec['cancelled_games']}; errors={totals['errors']}"
        )
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
