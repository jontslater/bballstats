#!/usr/bin/env python3
"""Report NBA prop mean bias by tier and P(over) calibration for a season."""
import json
import sys
from datetime import date
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.nba_prop_backtest import (
    graded_prediction_bias_report,
    run_nba_prop_backtest,
)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="NBA prop backtest / calibration report")
    parser.add_argument("--season", type=str, default="2025-26")
    parser.add_argument(
        "--stat-types",
        type=str,
        default="points,rebounds,assists,pts+ast+reb",
    )
    parser.add_argument(
        "--pit",
        action="store_true",
        help="Force point-in-time on-the-fly predictions (ignore saved rows)",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Limit PIT samples (for faster runs)",
    )
    parser.add_argument(
        "--graded-bias",
        action="store_true",
        help="Report before/after tier bias on saved graded predictions",
    )
    parser.add_argument("--date-start", type=str, default=None)
    parser.add_argument("--date-end", type=str, default=None)
    args = parser.parse_args()
    stat_types = [s.strip() for s in args.stat_types.split(",") if s.strip()]

    db = SessionLocal()
    try:
        if args.graded_bias:
            ds = date.fromisoformat(args.date_start) if args.date_start else None
            de = date.fromisoformat(args.date_end) if args.date_end else None
            out = graded_prediction_bias_report(
                db,
                args.season,
                stat_types=stat_types,
                date_start=ds,
                date_end=de,
            )
            print(json.dumps(out, indent=2))
            return 0

        report = run_nba_prop_backtest(
            db,
            args.season,
            stat_types=stat_types,
            pit=True if args.pit else None,
            max_samples=args.max_samples,
        )
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
