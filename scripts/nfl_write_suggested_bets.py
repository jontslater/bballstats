#!/usr/bin/env python3
"""
Generate and persist NFL suggested bets for upcoming game dates.

Usage:
    PYTHONUTF8=1 python scripts/nfl_write_suggested_bets.py
    PYTHONUTF8=1 python scripts/nfl_write_suggested_bets.py --date 2026-10-18
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.historical_tracking_service import HistoricalTrackingService
from app.services.suggested_bets import SuggestedBetsService


def write_for_date(db, game_date: date, limit: int = 15) -> int:
    service = SuggestedBetsService(db, sport="NFL")
    bets = service.get_suggested_bets(
        game_date=game_date,
        limit=limit,
        min_probability=0.55,
        include_long_shots=False,
    )
    if not bets:
        print(f"No NFL suggested bets for {game_date}")
        return 0

    tracker = HistoricalTrackingService(db)
    saved = tracker.save_suggested_bets(bets, game_date)

    print(f"\nNFL picks for {game_date} ({len(bets)} shown, {saved} saved):")
    for bet in bets:
        be = bet.get("break_even_american_odds")
        be_str = f"{be}" if be is not None else "N/A"
        hv = " [HIGH VARIANCE]" if bet.get("high_variance") else ""
        print(
            f"  {bet['player_name']} ({bet['player_team']}) {bet['stat_type']} "
            f"O{bet['line']:.1f} p={bet['probability']:.3f} break-even={be_str}{hv}"
        )
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, help="YYYY-MM-DD (default: today through +7 days)")
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.date:
            dates = [date.fromisoformat(args.date)]
        else:
            start = date.today()
            dates = [start + timedelta(days=i) for i in range(8)]

        total = 0
        for d in dates:
            total += write_for_date(db, d, limit=args.limit)
        print(json.dumps({"saved": total}))
    finally:
        db.close()


if __name__ == "__main__":
    main()
