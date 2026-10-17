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
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


MEDIAN_FAIRNESS_STATS = (
    "receptions",
    "receiving_yards",
    "rushing_yards",
    "passing_yards",
)

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


def median_betting_line(player_median: float, stat_type: Optional[str] = None) -> float:
    """Half-point line near the player's historical median (for calibration checks)."""
    if player_median <= 1:
        return 0.5
    if stat_type == "rushing_yards":
        lo = math.floor(player_median) + 0.5
        hi = math.ceil(player_median) - 0.5
        if hi < 0.5:
            hi = 0.5
        if abs(player_median - lo) <= abs(player_median - hi):
            return float(lo)
        return float(hi)
    return round(player_median * 2) / 2 - 0.5


def stat_value(row, col: str) -> float:
    if col == "anytime_td":
        return player_td_total(row)
    val = row.get(col)
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return 0.0
    return float(val)


def _league_mean_for_row(stat_name: str, row, player_mean: float) -> float:
    from app.services.nfl_position_priors import fallback_mean, role_for_position

    pos = row.get("position") if hasattr(row, "get") else None
    role = role_for_position(pos)
    fb = fallback_mean(stat_name, role)
    if fb is not None:
        return fb
    return player_mean


def collect_walk_forward_pairs(
    seasons: List[int],
    max_week: int = 18,
    min_history: int = 5,
    apply_posthoc: bool = False,
) -> Dict[str, List[Tuple[float, int]]]:
    calc = CalibratedProbabilityCalculator(sport="NFL")
    extended = sorted(set(seasons + [s - 1 for s in seasons]))
    df = load_nflverse_player_stats(extended)
    df = df[df["season_type"] == "REG"].copy()
    pairs: Dict[str, List[Tuple[float, int]]] = {k: [] for k in STAT_CONFIG}

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
                    prior = df[(df["player_id"] == pid) & (df["season"] < season)].sort_values(
                        ["season", "week"]
                    )
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

                    league_mean = _league_mean_for_row(stat_name, row, player_mean)
                    actual = stat_value(row, col)
                    player_median = float(statistics.median(hist_vals))
                    median_line = median_betting_line(player_median, stat_name)
                    eval_lines = list(set(lines + [median_line]))

                    for line in eval_lines:
                        out = calc.calculate_probability_for_line(
                            line=float(line),
                            player_mean=player_mean,
                            player_std=player_std,
                            sample_size=len(hist_vals),
                            stat_type=stat_name,
                            league_mean=league_mean,
                            league_std=None,
                            player_median=player_median,
                            apply_posthoc=apply_posthoc,
                        )
                        p = out["probability"]
                        hit = 1 if actual > line else 0
                        pairs[stat_name].append((p, hit))
    return pairs


def walk_forward(seasons: List[int], max_week: int, min_history: int = 5, silent: bool = False):
    calc = CalibratedProbabilityCalculator(sport="NFL")
    extended = sorted(set(seasons + [s - 1 for s in seasons]))
    df = load_nflverse_player_stats(extended)
    df = df[df["season_type"] == "REG"].copy()
    if df.empty:
        if not silent:
            print("WARNING: No nflverse player stats loaded.")
        return {}
    if not silent:
        print(f"Loaded nflverse rows: {len(df)} seasons={sorted(df['season'].unique())}")

    results = {
        name: {
            "pairs": [],
            "pairs_raw": [],
            "median_pairs": [],
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

                    league_mean = _league_mean_for_row(stat_name, row, player_mean)
                    actual = stat_value(row, col)
                    player_median = float(statistics.median(hist_vals))
                    median_line = median_betting_line(player_median, stat_name)

                    for line in lines:
                        out_raw = calc.calculate_probability_for_line(
                            line=float(line),
                            player_mean=player_mean,
                            player_std=player_std,
                            sample_size=len(hist_vals),
                            stat_type=stat_name if stat_name != "attempts" else "attempts",
                            league_mean=league_mean,
                            league_std=None,
                            player_median=player_median,
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
                            player_median=player_median,
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

                    med_out = calc.calculate_probability_for_line(
                        line=float(median_line),
                        player_mean=player_mean,
                        player_std=player_std,
                        sample_size=len(hist_vals),
                        stat_type=stat_name,
                        league_mean=league_mean,
                        player_median=player_median,
                        apply_posthoc=True,
                    )
                    results[stat_name]["median_pairs"].append(med_out["probability"])

    if not silent:
        print("=" * 80)
        print("NFL WALK-FORWARD CALIBRATION (nflverse → production calculator)")
        print("=" * 80)
    for stat_name, data in results.items():
        pairs = data["pairs"]
        if not pairs:
            if not silent:
                print(f"\n{stat_name}: no samples")
            continue
        raw_pairs = data["pairs_raw"]
        med = data["median_pairs"]
        med_avg = sum(med) / len(med) if med else 0.0
        data["brier_raw"] = brier(raw_pairs)
        data["brier_posthoc"] = brier(pairs)
        data["median_avg"] = med_avg
        if not silent:
            print(
                f"\n{stat_name}: n={len(pairs)} "
                f"Brier_raw={data['brier_raw']:.4f} Brier_posthoc={data['brier_posthoc']:.4f} "
                f"median_line_avg_p_over={med_avg:.3f}"
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
    return results


def compute_median_p_over(
    seasons: List[int],
    max_week: int = 18,
    min_history: int = 5,
) -> Dict[str, float]:
    """Average model P(over) at each player's median line (post-hoc on)."""
    calc = CalibratedProbabilityCalculator(sport="NFL")
    extended = sorted(set(seasons + [s - 1 for s in seasons]))
    df = load_nflverse_player_stats(extended)
    df = df[df["season_type"] == "REG"].copy()
    medians: Dict[str, List[float]] = {s: [] for s in MEDIAN_FAIRNESS_STATS}

    for season in seasons:
        season_df = df[df["season"] == season].sort_values(["player_id", "week"])
        for week in sorted(season_df["week"].unique()):
            if week > max_week:
                continue
            for _, row in season_df[season_df["week"] == week].iterrows():
                pid = row["player_id"]
                history = season_df[(season_df["player_id"] == pid) & (season_df["week"] < week)]
                if len(history) < min_history:
                    prior = df[(df["player_id"] == pid) & (df["season"] < season)].sort_values(
                        ["season", "week"]
                    )
                    history = prior.tail(min_history * 3)
                if len(history) < min_history:
                    continue
                for stat_name in MEDIAN_FAIRNESS_STATS:
                    col, _lines = STAT_CONFIG[stat_name]
                    hist_vals = [stat_value(r, col) for _, r in history.iterrows()]
                    if not hist_vals or max(hist_vals) <= 0:
                        continue
                    player_mean = sum(hist_vals) / len(hist_vals)
                    player_median = float(statistics.median(hist_vals))
                    if len(hist_vals) > 1:
                        var = sum((v - player_mean) ** 2 for v in hist_vals) / (len(hist_vals) - 1)
                        player_std = var ** 0.5
                    else:
                        player_std = max(player_mean * 0.25, 1.0)
                    league_mean = _league_mean_for_row(stat_name, row, player_mean)
                    median_line = median_betting_line(player_median, stat_name)
                    out = calc.calculate_probability_for_line(
                        line=float(median_line),
                        player_mean=player_mean,
                        player_std=player_std,
                        sample_size=len(hist_vals),
                        stat_type=stat_name,
                        league_mean=league_mean,
                        player_median=player_median,
                        apply_posthoc=True,
                    )
                    medians[stat_name].append(out["probability"])
    return {k: sum(v) / len(v) for k, v in medians.items() if v}


def assert_median_fairness(
    averages: Dict[str, float],
    low: float = 0.45,
    high: float = 0.55,
) -> None:
    for stat in MEDIAN_FAIRNESS_STATS:
        if stat not in averages:
            continue
        avg = averages[stat]
        if not (low <= avg <= high):
            raise AssertionError(
                f"{stat} median-line avg P(over)={avg:.3f} outside [{low}, {high}]"
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
