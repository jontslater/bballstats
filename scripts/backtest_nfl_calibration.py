#!/usr/bin/env python3
"""
Walk-forward calibration backtest for NFL player props using nflverse weekly stats
and the production CalibratedProbabilityCalculator.

Usage:
    python scripts/backtest_nfl_calibration.py
    python scripts/backtest_nfl_calibration.py --seasons 2025 2026 --max-week 8
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.services.nfl_data import load_nflverse_player_stats


def bucket_probability(prob: float) -> str:
    if prob < 0.50:
        return "0.00-0.49"
    elif prob < 0.55:
        return "0.50-0.54"
    elif prob < 0.60:
        return "0.55-0.59"
    elif prob < 0.65:
        return "0.60-0.64"
    elif prob < 0.70:
        return "0.65-0.69"
    elif prob < 0.75:
        return "0.70-0.74"
    elif prob < 0.80:
        return "0.75-0.79"
    elif prob < 0.85:
        return "0.80-0.84"
    elif prob < 0.90:
        return "0.85-0.89"
    return "0.90-1.00"


def brier(pairs: List[Tuple[float, int]]) -> float:
    if not pairs:
        return 0.0
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


STAT_CONFIG = {
    "receptions": ("receptions", [2.5, 4.5, 6.5]),
    "receiving_yards": ("receiving_yards", [39.5, 59.5, 79.5]),
    "rushing_yards": ("rushing_yards", [39.5, 59.5, 79.5]),
    "passing_yards": ("passing_yards", [199.5, 224.5, 249.5]),
    "completions": ("completions", [19.5, 22.5]),
    "attempts": ("attempts", [29.5, 34.5]),
    "anytime_td": ("anytime_td", [0.5]),
}


def player_td_total(row) -> float:
    return float((row.get("rushing_tds") or 0) + (row.get("receiving_tds") or 0))


def stat_value(row, col: str) -> float:
    if col == "anytime_td":
        return player_td_total(row)
    val = row.get(col)
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return 0.0
    return float(val)


def walk_forward(seasons: List[int], max_week: int, min_history: int = 5):
    calc = CalibratedProbabilityCalculator(sport="NFL")
    # Include prior season for early-week history when nflverse lags current year.
    extended = sorted(set(seasons + [s - 1 for s in seasons]))
    df = load_nflverse_player_stats(extended)
    df = df[df["season_type"] == "REG"].copy()
    if df.empty:
        print("WARNING: No nflverse player stats loaded.")
        return
    print(f"Loaded nflverse rows: {len(df)} seasons={sorted(df['season'].unique())}")

    results = {
        name: {
            "pairs": [],
            "pairs_raw": [],
            "buckets": defaultdict(lambda: {"n": 0, "hits": 0, "sum_p": 0.0}),
        }
        for name in STAT_CONFIG
    }

    for season in seasons:
        season_df = df[df["season"] == season].sort_values(["player_id", "week"])
        for week in sorted(season_df["week"].unique()):
            if week > max_week:
                continue
            test_rows = season_df[season_df["week"] == week]
            for _, row in test_rows.iterrows():
                pid = row["player_id"]
                history = season_df[(season_df["player_id"] == pid) & (season_df["week"] < week)]
                if len(history) < min_history:
                    prior = df[
                        (df["player_id"] == pid)
                        & (df["season"] < season)
                    ].sort_values(["season", "week"])
                    history = prior.tail(min_history * 3)
                if len(history) < min_history:
                    continue

                for stat_name, (col, lines) in STAT_CONFIG.items():
                    hist_vals = [stat_value(r, col) for _, r in history.iterrows()]
                    if col in ("passing_yards", "completions", "attempts") and max(hist_vals) <= 0:
                        continue
                    if col in ("rushing_yards", "rushing_attempts") and max(hist_vals) <= 0:
                        continue
                    if col in ("receptions", "receiving_yards") and max(hist_vals) <= 0:
                        continue

                    player_mean = sum(hist_vals) / len(hist_vals)
                    if len(hist_vals) > 1:
                        var = sum((v - player_mean) ** 2 for v in hist_vals) / (len(hist_vals) - 1)
                        player_std = var ** 0.5
                    else:
                        player_std = max(player_mean * 0.25, 1.0)

                    league_mean = sum(hist_vals) / len(hist_vals)
                    actual = stat_value(row, col)

                    for line in lines:
                        out_raw = calc.calculate_probability_for_line(
                            line=float(line),
                            player_mean=player_mean,
                            player_std=player_std,
                            sample_size=len(hist_vals),
                            stat_type=stat_name if stat_name != "attempts" else "attempts",
                            league_mean=league_mean,
                            league_std=None,
                            apply_posthoc=False,
                        )
                        out = calc.calculate_probability_for_line(
                            line=float(line),
                            player_mean=player_mean,
                            player_std=player_std,
                            sample_size=len(hist_vals),
                            stat_type=stat_name if stat_name != "attempts" else "attempts",
                            league_mean=league_mean,
                            league_std=None,
                            apply_posthoc=True,
                        )
                        p = out["probability"]
                        p_raw = out_raw["probability"]
                        hit = 1 if actual > line else 0
                        results[stat_name]["pairs"].append((p, hit))
                        results[stat_name]["pairs_raw"].append((p_raw, hit))
                        b = bucket_probability(p)
                        results[stat_name]["buckets"][b]["n"] += 1
                        results[stat_name]["buckets"][b]["hits"] += hit
                        results[stat_name]["buckets"][b]["sum_p"] += p

    print("=" * 80)
    print("NFL WALK-FORWARD CALIBRATION (nflverse → production calculator)")
    print("=" * 80)
    for stat_name, data in results.items():
        pairs = data["pairs"]
        if not pairs:
            print(f"\n{stat_name}: no samples")
            continue
        raw_pairs = data["pairs_raw"]
        print(
            f"\n{stat_name}: n={len(pairs)} "
            f"Brier_raw={brier(raw_pairs):.4f} Brier_posthoc={brier(pairs):.4f}"
        )
        for bucket in sorted(data["buckets"].keys()):
            b = data["buckets"][bucket]
            if b["n"] == 0:
                continue
            actual_rate = b["hits"] / b["n"]
            avg_p = b["sum_p"] / b["n"]
            print(
                f"  bucket {bucket}: n={b['n']:4d} avg_p={avg_p:.3f} actual={actual_rate:.3f} gap={actual_rate - avg_p:+.3f}"
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=[2024, 2025, 2026],
        help="Test seasons (nflverse may only include completed years; 2024 always works)",
    )
    parser.add_argument("--max-week", type=int, default=8, help="Last week included in 2026 early-season test")
    parser.add_argument("--min-history", type=int, default=5)
    args = parser.parse_args()
    walk_forward(args.seasons, args.max_week, args.min_history)


if __name__ == "__main__":
    main()
