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

from app.services.nfl_posthoc_calibration import NFLPosthocCalibrator


def main():
    seasons = [2024, 2025]
    pairs_by_stat: Dict[str, List[Tuple[float, int]]] = collect_walk_forward_pairs(
        seasons, max_week=18, min_history=5, apply_posthoc=False
    )
    calibrator = NFLPosthocCalibrator()
    maps = {}
    for stat, stat_pairs in pairs_by_stat.items():
        fitted = calibrator.fit_symmetric_alpha(stat_pairs, min_samples=150)
        if fitted:
            maps[stat] = fitted
    calibrator.save(
        maps,
        meta={"seasons": seasons, "method": "symmetric_alpha_walk_forward", "model": "production_v2"},
    )
    enabled = sum(1 for m in maps.values() if m.get("enabled"))
    print(f"Wrote {calibrator.params_path} with {len(maps)} stats ({enabled} enabled)")


if __name__ == "__main__":
    main()
