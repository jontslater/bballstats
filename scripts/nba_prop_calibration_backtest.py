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
    fit_and_save_calibration,
    graded_prediction_bias_report,
    run_nba_prop_backtest,
    validate_calibration,
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
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--sample-strategy",
        choices=("random", "stride"),
        default="random",
    )
    parser.add_argument(
        "--apply-tier-subtract",
        action="store_true",
        help="Apply tier subtract from calibration JSON when scoring PIT rows",
    )
    parser.add_argument(
        "--no-prob-calibrate",
        action="store_true",
        help="Use raw P(over) without shrink calibration",
    )
    parser.add_argument(
        "--fit-calibration",
        action="store_true",
        help="Fit tier subtract + prob shrink on 2025-26 PIT and save JSON",
    )
    parser.add_argument(
        "--validate-calibration",
        action="store_true",
        help="Run PIT on --season with saved calibration (default 2026-27)",
    )
    parser.add_argument(
        "--graded-bias",
        action="store_true",
        help="Report bias on saved graded predictions (minutes-only vs saved subtract)",
    )
    parser.add_argument("--date-start", type=str, default=None)
    parser.add_argument("--date-end", type=str, default=None)
    args = parser.parse_args()
    stat_types = [s.strip() for s in args.stat_types.split(",") if s.strip()]

    db = SessionLocal()
    try:
        if args.fit_calibration:
            out = fit_and_save_calibration(
                db,
                train_season="2025-26",
                stat_types=stat_types,
                max_samples=args.max_samples or 400,
                seed=args.seed,
                sample_strategy=args.sample_strategy,
            )
            val = validate_calibration(
                db,
                season_year="2026-27",
                stat_types=stat_types,
                max_samples=args.max_samples or 400,
                seed=args.seed,
                sample_strategy=args.sample_strategy,
            )
            print(json.dumps({"fit": out, "validate_2026_27": val}, indent=2))
            return 0

        if args.validate_calibration:
            out = validate_calibration(
                db,
                season_year=args.season,
                stat_types=stat_types,
                max_samples=args.max_samples or 400,
                seed=args.seed,
                sample_strategy=args.sample_strategy,
            )
            print(json.dumps(out, indent=2))
            return 0

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
            seed=args.seed,
            sample_strategy=args.sample_strategy,
            apply_tier_subtract=args.apply_tier_subtract,
            calibrate_prob=not args.no_prob_calibrate,
        )
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
