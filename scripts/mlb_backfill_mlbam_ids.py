#!/usr/bin/env python3
"""
Backfill Player.mlbam_id for MLB players using Stats API + Savant name matching.

Run after schema migration and before Statcast/luck backtests:
    set DATABASE_URL=postgresql://...@localhost:5433/nba_betting
    set PYTHONPATH=backend
    python scripts/mlb_backfill_mlbam_ids.py --season 2026
    python scripts/mlb_backfill_mlbam_ids.py --season 2026 --dry-run
"""
import argparse
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.database import SessionLocal
from app.services.mlb_player_mapping import backfill_mlbam_ids


def main():
    parser = argparse.ArgumentParser(description="Backfill MLBAM ids on MLB players")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-score", type=float, default=4.0)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        stats = backfill_mlbam_ids(
            db,
            args.season,
            dry_run=args.dry_run,
            min_score=args.min_score,
        )
        mapped = stats["matched"]
        total_missing = stats["examined"]
        print(
            f"MLBAM backfill ({'dry-run' if args.dry_run else 'applied'}): "
            f"matched={mapped} examined={total_missing} "
            f"conflicts={stats['skipped_conflict']} unmatched={stats['unmatched']}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
