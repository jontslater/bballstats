"""
Load / save NBA prop calibration (tier mean subtract, P(over) shrink) fit on PIT backtests.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

_DEFAULT: Dict[str, Any] = {
    "fit_season": None,
    "tier_subtract": {},
    "prob_shrink": 1.0,
}

_CACHE: Optional[Dict[str, Any]] = None


def calibration_file_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "nba_prop_calibration.json"


def load_calibration(*, reload: bool = False) -> Dict[str, Any]:
    global _CACHE
    if _CACHE is not None and not reload:
        return _CACHE
    path = calibration_file_path()
    if not path.is_file():
        _CACHE = dict(_DEFAULT)
        return _CACHE
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(_DEFAULT)
    merged.update(data)
    _CACHE = merged
    return _CACHE


def save_calibration(data: Mapping[str, Any]) -> Path:
    global _CACHE
    path = calibration_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    out = dict(_DEFAULT)
    out.update(data)
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    _CACHE = out
    return path


def get_tier_subtract_offsets() -> Dict[str, float]:
    raw = load_calibration().get("tier_subtract") or {}
    return {str(k): float(v) for k, v in raw.items() if v}


def get_prob_shrink() -> float:
    val = load_calibration().get("prob_shrink", 1.0)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 1.0
