"""Position/role-specific NFL league priors for shrinkage and calibration."""
from __future__ import annotations

from typing import Dict, Optional, Set

# Map player.position to role bucket for league averages
POSITION_ROLE: Dict[str, str] = {
    "QB": "QB",
    "RB": "RB",
    "FB": "RB",
    "WR": "WR",
    "TE": "TE",
}

STAT_ROLE_FILTER: Dict[str, Set[str]] = {
    "passing_yards": {"QB"},
    "passing_tds": {"QB"},
    "completions": {"QB"},
    "attempts": {"QB"},
    "pass_attempts": {"QB"},
    "interceptions": {"QB"},
    "rushing_yards": {"QB", "RB", "WR", "TE"},
    "rushing_attempts": {"QB", "RB", "WR", "TE"},
    "rushing_tds": {"QB", "RB", "WR", "TE"},
    "receptions": {"RB", "WR", "TE"},
    "receiving_yards": {"RB", "WR", "TE"},
    "receiving_tds": {"RB", "WR", "TE"},
    "targets": {"RB", "WR", "TE"},
    "anytime_td": {"QB", "RB", "WR", "TE"},
}

# Fallback league per-game rates when DB is sparse (role-specific)
ROLE_FALLBACK_MEAN: Dict[str, Dict[str, float]] = {
    "QB": {
        "passing_yards": 220.0,
        "completions": 21.0,
        "attempts": 32.0,
        "pass_attempts": 32.0,
        "rushing_yards": 18.0,
        "rushing_attempts": 4.0,
        "anytime_td": 0.15,
    },
    "RB": {
        "rushing_yards": 55.0,
        "rushing_attempts": 12.0,
        "receptions": 2.5,
        "receiving_yards": 18.0,
        "anytime_td": 0.45,
    },
    "WR": {
        "receptions": 4.5,
        "receiving_yards": 55.0,
        "targets": 7.0,
        "rushing_yards": 3.0,
        "anytime_td": 0.35,
    },
    "TE": {
        "receptions": 3.5,
        "receiving_yards": 38.0,
        "targets": 5.0,
        "anytime_td": 0.30,
    },
}


def role_for_position(position: Optional[str]) -> Optional[str]:
    if not position:
        return None
    pos = position.upper()
    if pos in POSITION_ROLE:
        return POSITION_ROLE[pos]
    if pos in ("HB",):
        return "RB"
    return None


def positions_for_stat_role(stat_type: str, role: Optional[str]) -> Optional[Set[str]]:
    if role:
        allowed = STAT_ROLE_FILTER.get(stat_type)
        if allowed and role not in allowed:
            return set()
        return {role} if role in POSITION_ROLE else {role}
    return STAT_ROLE_FILTER.get(stat_type)


def fallback_mean(stat_type: str, role: Optional[str]) -> Optional[float]:
    if not role:
        return None
    return ROLE_FALLBACK_MEAN.get(role, {}).get(stat_type)
