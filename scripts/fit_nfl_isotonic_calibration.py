#!/usr/bin/env python3
"""Fit walk-forward symmetric NFL post-hoc calibration (per-stat, only if Brier improves)."""
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
collect_walk_forward_pairs = _mod.collect_walk_forward_pairs
walk_forward = _mod.walk_forward

from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.services.nfl_posthoc_calibration import NFLPosthocCalibrator


def _brier(pairs, alpha: float = 1.0) -> float:
    if not pairs:
        return 0.0
    total = 0.0
    for p_raw, y in pairs:
        p = max(0.01, min(0.99, 0.5 + alpha * (p_raw - 0.5)))
        total += (p - y) ** 2
    return total / len(pairs)


def main():
    seasons = [2024]
    pairs_by_stat: Dict[str, List[Tuple[float, int]]] = collect_walk_forward_pairs(
        seasons, max_week=18, min_history=5, apply_posthoc=False
    )
    calibrator = NFLPosthocCalibrator()
    maps = {}
    for stat, stat_pairs in pairs_by_stat.items():
        fitted = calibrator.fit_symmetric_alpha_holdout(stat_pairs, min_samples=150)
        if fitted and fitted.get("enabled"):
            alpha = float(fitted.get("alpha", 1.0))
            raw_b = _brier(stat_pairs, 1.0)
            cal_b = _brier(stat_pairs, alpha)
            if cal_b >= raw_b - 0.0005:
                fitted = {
                    **fitted,
                    "enabled": False,
                    "alpha": 1.0,
                    "brier_raw": round(raw_b, 5),
                    "brier_cal": round(raw_b, 5),
                }
        if fitted:
            maps[stat] = fitted
    calibrator.save(
        maps,
        meta={"seasons": seasons, "method": "symmetric_alpha_walk_forward", "model": "production_v3"},
    )
    # Disable any stat whose post-hoc hurts on standard-line 2024 walk-forward
    CalibratedProbabilityCalculator._nfl_posthoc = None  # reload maps
    from app.services.calibrated_probability import CalibratedProbabilityCalculator as CPC

    CPC._nfl_posthoc = None
    summary = walk_forward(seasons, max_week=18, min_history=5, silent=True)
    for stat, entry in maps.items():
        if not entry.get("enabled"):
            continue
        data = summary.get(stat) or {}
        br = data.get("brier_raw")
        bp = data.get("brier_posthoc")
        if br is not None and bp is not None and bp >= br - 0.0001:
            entry["enabled"] = False
            entry["alpha"] = 1.0
    calibrator.save(
        maps,
        meta={"seasons": seasons, "method": "symmetric_alpha_walk_forward", "model": "production_v3"},
    )
    enabled = sum(1 for m in maps.values() if m.get("enabled"))
    print(f"Wrote {calibrator.params_path} with {len(maps)} stats ({enabled} enabled)")


if __name__ == "__main__":
    main()
