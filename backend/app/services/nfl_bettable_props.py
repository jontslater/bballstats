"""
NFL props eligible for suggested bets, driven by calibration holdout + NFL_BETTABLE_PROPS env.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

# Default: props that passed 2025–26 style holdout (yardage + receptions; excludes
# completions, attempts, rushing_attempts, anytime_td when calibration fails).
DEFAULT_NFL_BETTABLE_PROPS: List[str] = [
    "receptions",
    "receiving_yards",
    "rushing_yards",
    "passing_yards",
]

_CALIB_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "nfl_isotonic_calibration.json"
)


def _parse_env_allowlist() -> Optional[List[str]]:
    raw = os.environ.get("NFL_BETTABLE_PROPS", "").strip()
    if not raw:
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]


def _bettable_from_calibration_file() -> Optional[List[str]]:
    if not _CALIB_PATH.exists():
        return None
    try:
        data = json.loads(_CALIB_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    meta = data.get("meta") or {}
    if meta.get("bettable_props"):
        return list(meta["bettable_props"])
    stats = data.get("stats") or {}
    derived = [k for k, v in stats.items() if v.get("bettable")]
    return derived if derived else None


def get_nfl_bettable_stat_types() -> List[str]:
    """
    Props to surface in suggested bets and primary NFL bet flows.
    Priority: NFL_BETTABLE_PROPS env → calibration JSON → built-in default.
    """
    env_list = _parse_env_allowlist()
    if env_list is not None:
        return env_list
    from_file = _bettable_from_calibration_file()
    if from_file:
        return from_file
    return list(DEFAULT_NFL_BETTABLE_PROPS)


def is_nfl_stat_bettable(stat_type: str) -> bool:
    return stat_type in get_nfl_bettable_stat_types()
