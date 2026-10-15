#!/usr/bin/env python3
"""
Backfill NFL games + player weekly stats from nflverse CSV releases.

Usage:
    PYTHONUTF8=1 python scripts/nfl_backfill_player_stats.py --seasons 2025 2026
    PYTHONUTF8=1 python scripts/nfl_backfill_player_stats.py --seasons 2025 2026 --no-skip-existing
"""
import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.nfl_results import backfill_from_nflverse


def main():
    parser = argparse.ArgumentParser(description="Backfill NFL stats from nflverse")
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=[2025, 2026],
        help="Season years to import (default: 2025 2026)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Import even when player-game rows already exist",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = backfill_from_nflverse(
            db,
            seasons=args.seasons,
            skip_existing=not args.no_skip_existing,
        )
        print("Backfill complete:")
        for k, v in result.items():
            print(f"  {k}: {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
