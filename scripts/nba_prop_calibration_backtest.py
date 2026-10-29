#!/usr/bin/env python3
"""Report NBA prop mean bias by tier and P(over) calibration for a season."""
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.nba_prop_backtest import run_nba_prop_backtest


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="NBA prop backtest / calibration report")
    parser.add_argument("--season", type=str, default="2025-26")
    parser.add_argument(
        "--stat-types",
        type=str,
        default="points,rebounds,assists,pts+ast+reb",
    )
    args = parser.parse_args()
    stat_types = [s.strip() for s in args.stat_types.split(",") if s.strip()]

    db = SessionLocal()
    try:
        report = run_nba_prop_backtest(db, args.season, stat_types=stat_types)
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
