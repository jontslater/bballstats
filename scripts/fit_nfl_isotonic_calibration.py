#!/usr/bin/env python3
"""Fit NFL post-hoc on 2024–2025; select on 2025; evaluate holdout 2026 weeks 1–6."""
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
from app.services.nfl_calibration_metrics import (
    aggregate_bucket_stats,
    format_bucket_table,
    prop_passes_bettable_criteria,
)
from app.services.nfl_posthoc_calibration import NFLPosthocCalibrator


def _holdout_report() -> dict:
    CalibratedProbabilityCalculator._nfl_posthoc = None
    return walk_forward([2026], max_week=6, min_history=5, silent=True)


def main():
    train, selection = collect_calibration_train_val_pairs(min_history=5)
    calibrator = NFLPosthocCalibrator()
    maps = {}
    for stat in train.keys():
        fitted = calibrator.fit_prop_calibration(
            train.get(stat) or [],
            selection.get(stat) or [],
            min_train=100,
            min_val=80,
        )
        if fitted:
            maps[stat] = fitted

    meta = {
        "train": "2024 + all 2025 (fit pool)",
        "selection": "2025 season only (hyperparameter grid search)",
        "holdout": "2026 weeks 1–6 (true OOS evaluation)",
        "method": "symmetric_alpha_plus_high_bucket",
        "model": "production_v6",
    }
    calibrator.save(maps, meta=meta)

    holdout = _holdout_report()
    bettable_props = []
    print("=" * 80)
    print("TRUE HOLDOUT: 2026 weeks 1–6 (parameters selected on 2025 only)")
    print("=" * 80)
    for stat, data in holdout.items():
        pairs = data.get("pairs") or []
        if not pairs:
            continue
        raw_pairs = data.get("pairs_raw") or []
        buckets = aggregate_bucket_stats(pairs)
        med_avg = data.get("median_avg", 0.0)
        br = data.get("brier_raw", 0.0)
        bp = data.get("brier_posthoc", 0.0)
        passes, fail_reasons = prop_passes_bettable_criteria(
            median_avg_p_over=med_avg,
            buckets=buckets,
            brier_raw=br,
            brier_posthoc=bp,
        )
        entry = maps.get(stat) or {}
        entry["bettable"] = bool(passes)
        entry["bettable_fail_reasons"] = fail_reasons
        entry["oos_median_p_over"] = round(med_avg, 4)
        entry["oos_brier_raw"] = round(br, 5)
        entry["oos_brier_posthoc"] = round(bp, 5)
        entry["oos_buckets"] = {
            k: {
                "n": int(v["n"]),
                "mean_predicted": round(v["mean_predicted"], 4),
                "actual_hit_rate": round(v["actual_hit_rate"], 4),
                "gap": round(v["gap"], 4),
            }
            for k, v in buckets.items()
        }
        if passes:
            bettable_props.append(stat)
        if not passes and (entry.get("enabled") or entry.get("high_enabled")):
            entry["enabled"] = False
            entry["high_enabled"] = False
            entry["alpha"] = 1.0

        print(
            f"\n{stat}: n={len(pairs)} "
            f"Brier_raw={br:.4f} Brier_posthoc={bp:.4f} "
            f"median_line_P(over)={med_avg:.3f} bettable={passes}"
        )
        if fail_reasons:
            print("  fail:", "; ".join(fail_reasons))
        print(format_bucket_table(buckets))

    meta["bettable_props"] = bettable_props
    calibrator.save(maps, meta=meta)

    enabled = sum(1 for m in maps.values() if m.get("enabled") or m.get("high_enabled"))
    print(f"\nWrote {calibrator.params_path} — active calibration: {enabled}/{len(maps)}")
    print(f"Suggested-bet allowlist: {','.join(bettable_props) or '(none)'}")


if __name__ == "__main__":
    main()
