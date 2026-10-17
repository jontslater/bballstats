#!/usr/bin/env python3
"""Fit NFL post-hoc on data through 2025; validate on 2026 weeks 1–6 only."""
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
report_oos_2026_scores = _mod.report_oos_2026_scores

from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.services.nfl_bettable_props import DEFAULT_NFL_BETTABLE_PROPS
from app.services.nfl_posthoc_calibration import NFLPosthocCalibrator


def _mark_bettable(maps: dict, oos_results: dict) -> list:
    """Props where post-hoc helps or matches raw on 2026 w1–6."""
    bettable = []
    for stat, entry in maps.items():
        data = oos_results.get(stat) or {}
        br = data.get("brier_raw")
        bp = data.get("brier_posthoc")
        passes = False
        if br is not None and bp is not None:
            passes = bp < br - 0.0005
            if not passes and stat in DEFAULT_NFL_BETTABLE_PROPS and bp <= br + 0.0001:
                passes = True
        entry["bettable"] = bool(passes)
        entry["oos_brier_raw"] = round(br, 5) if br is not None else None
        entry["oos_brier_posthoc"] = round(bp, 5) if bp is not None else None
        if passes:
            bettable.append(stat)
    if not bettable:
        bettable = list(DEFAULT_NFL_BETTABLE_PROPS)
        for stat in bettable:
            if stat in maps:
                maps[stat]["bettable"] = True
    return bettable


def main():
    train, val = collect_calibration_train_val_pairs(min_history=5)
    calibrator = NFLPosthocCalibrator()
    maps = {}
    for stat in train.keys():
        fitted = calibrator.fit_prop_calibration(
            train.get(stat) or [],
            val.get(stat) or [],
            min_train=100,
            min_val=40,
        )
        if fitted:
            maps[stat] = fitted

    meta = {
        "train": "2024 + all 2025 (through week 18)",
        "val": "2026 weeks 1–6 only",
        "method": "symmetric_alpha_plus_high_bucket",
        "model": "production_v5",
    }
    calibrator.save(maps, meta=meta)

    CalibratedProbabilityCalculator._nfl_posthoc = None
    oos = report_oos_2026_scores(silent=True)
    for stat, entry in maps.items():
        if not (entry.get("enabled") or entry.get("high_enabled")):
            continue
        data = oos.get(stat) or {}
        br = data.get("brier_raw")
        bp = data.get("brier_posthoc")
        if br is not None and bp is not None and bp >= br - 0.0001:
            entry["enabled"] = False
            entry["high_enabled"] = False
            entry["alpha"] = 1.0

    bettable_props = _mark_bettable(maps, oos)
    meta["bettable_props"] = bettable_props
    calibrator.save(maps, meta=meta)

    report_oos_2026_scores(silent=False)
    enabled = sum(1 for m in maps.values() if m.get("enabled") or m.get("high_enabled"))
    print(f"Wrote {calibrator.params_path} — calibration active: {enabled}/7")
    print(f"Suggested-bet allowlist: {','.join(bettable_props)}")


if __name__ == "__main__":
    main()
