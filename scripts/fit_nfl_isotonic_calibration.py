#!/usr/bin/env python3
"""Fit walk-forward isotonic calibration maps for NFL props and write data/nfl_isotonic_calibration.json."""
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from collections import defaultdict
from typing import Dict, List, Tuple

import importlib.util

_backtest_path = Path(__file__).parent / "backtest_nfl_calibration.py"
_spec = importlib.util.spec_from_file_location("backtest_nfl_calibration", _backtest_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STAT_CONFIG = _mod.STAT_CONFIG
stat_value = _mod.stat_value

from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.services.nfl_data import load_nflverse_player_stats
from app.services.nfl_posthoc_calibration import NFLPosthocCalibrator


def collect_raw_pairs(seasons, max_week=18, min_history=5):
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
            for _, row in season_df[season_df["week"] == week].iterrows():
                pid = row["player_id"]
                history = season_df[(season_df["player_id"] == pid) & (season_df["week"] < week)]
                if len(history) < min_history:
                    prior = df[(df["player_id"] == pid) & (df["season"] < season)].sort_values(["season", "week"])
                    history = prior.tail(min_history * 3)
                if len(history) < min_history:
                    continue
                for stat_name, (col, lines) in STAT_CONFIG.items():
                    hist_vals = [stat_value(r, col) for _, r in history.iterrows()]
                    if not hist_vals or max(hist_vals) <= 0:
                        continue
                    player_mean = sum(hist_vals) / len(hist_vals)
                    var = sum((v - player_mean) ** 2 for v in hist_vals) / max(len(hist_vals) - 1, 1)
                    player_std = var ** 0.5
                    actual = stat_value(row, col)
                    for line in lines:
                        out = calc.calculate_probability_for_line(
                            line=float(line),
                            player_mean=player_mean,
                            player_std=player_std,
                            sample_size=len(hist_vals),
                            stat_type=stat_name,
                            league_mean=player_mean,
                            apply_posthoc=False,
                        )
                        pairs[stat_name].append((out["raw_probability"], 1 if actual > line else 0))
    return pairs


def main():
    seasons = [2024]
    pairs = collect_raw_pairs(seasons)
    calibrator = NFLPosthocCalibrator()
    maps = {}
    for stat, stat_pairs in pairs.items():
        fitted = calibrator.fit_isotonic(stat_pairs, min_samples=150)
        if fitted:
            maps[stat] = fitted
    calibrator.save(maps, meta={"seasons": seasons, "method": "isotonic_walk_forward"})
    print(f"Wrote {calibrator.params_path} with {len(maps)} stat maps")


if __name__ == "__main__":
    main()
