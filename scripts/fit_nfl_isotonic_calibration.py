#!/usr/bin/env python3
"""Fit walk-forward NFL post-hoc calibration on prior weeks; validate on 2025-26 holdout."""
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

import importlib.util

_backtest_path = Path(__file__).parent / "backtest_nfl_calibration.py"
_spec = importlib.util.spec_from_file_location("backtest_nfl_calibration", _backtest_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
collect_calibration_train_val_pairs = _mod.collect_calibration_train_val_pairs
walk_forward = _mod.walk_forward

from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.services.nfl_posthoc_calibration import NFLPosthocCalibrator


def main():
    train, val = collect_calibration_train_val_pairs(min_history=5)
    calibrator = NFLPosthocCalibrator()
    maps = {}
    for stat in train.keys():
        fitted = calibrator.fit_prop_calibration(
            train.get(stat) or [],
            val.get(stat) or [],
            min_train=100,
            min_val=60,
        )
        if fitted:
            maps[stat] = fitted

    meta = {
        "train": "2024 + 2025 weeks 1-8",
        "val": "2025 weeks 9-18 + 2026",
        "method": "symmetric_alpha_plus_high_bucket",
        "model": "production_v4",
    }
    calibrator.save(maps, meta=meta)

    CalibratedProbabilityCalculator._nfl_posthoc = None
    holdout = walk_forward([2025, 2026], max_week=18, min_history=5, silent=True)
    for stat, entry in maps.items():
        if not (entry.get("enabled") or entry.get("high_enabled")):
            continue
        data = holdout.get(stat) or {}
        br = data.get("brier_raw")
        bp = data.get("brier_posthoc")
        if br is not None and bp is not None and bp >= br - 0.0001:
            entry["enabled"] = False
            entry["high_enabled"] = False
            entry["alpha"] = 1.0
    calibrator.save(maps, meta=meta)

    enabled = sum(1 for m in maps.values() if m.get("enabled") or m.get("high_enabled"))
    print(f"Wrote {calibrator.params_path} with {len(maps)} stats ({enabled} with active calibration)")


if __name__ == "__main__":
    main()
