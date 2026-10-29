"""
Per-stat / tier mean bias correction for NBA prop predictions.

Learned offsets subtract from model mean (model was high vs actual).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Tuple

# Tier-only defaults from 2026-27 early-season graded bias (model - actual).
DEFAULT_TIER_BIAS_SUBTRACT: Dict[str, float] = {
    "star": 6.02,
    "rotation": 3.17,
    "bench": 1.47,
}

# Scale tier correction by stat magnitude (points vs counting stats).
STAT_TIER_SCALE: Dict[str, float] = {
    "points": 1.0,
    "pts+ast+reb": 1.0,
    "rebounds": 0.45,
    "assists": 0.45,
    "three_pointers_made": 0.35,
}


def player_tier_for_bias(mean: float, stat_type: str) -> str:
    if stat_type in ("points", "pts+ast+reb"):
        if mean >= 22:
            return "star"
        if mean >= 14:
            return "rotation"
        return "bench"
    if stat_type == "rebounds":
        return "star" if mean >= 9 else ("rotation" if mean >= 5 else "bench")
    if stat_type == "assists":
        return "star" if mean >= 7 else ("rotation" if mean >= 4 else "bench")
    return "rotation" if mean >= 2 else "bench"


def apply_mean_bias_correction(
    mean: float,
    stat_type: str,
    *,
    tier: Optional[str] = None,
    offsets: Optional[Mapping[str, float]] = None,
) -> float:
    """Subtract fitted tier bias (optionally scaled by stat type)."""
    if mean is None:
        return mean
    tier = tier or player_tier_for_bias(mean, stat_type)
    base = (offsets or DEFAULT_TIER_BIAS_SUBTRACT).get(tier, 0.0)
    scale = STAT_TIER_SCALE.get(stat_type, 0.5)
    corrected = mean - base * scale
    return round(max(corrected, 0.0), 2)


def fit_tier_bias_subtract(
    errors: List[Tuple[str, str, float]],
) -> Dict[str, float]:
    """
    Fit tier-only subtract offsets from (stat_type, tier, error) rows.
    error = model_mean - actual (positive => model too high).
    """
    by_tier: Dict[str, List[float]] = defaultdict(list)
    for _stat, tier, err in errors:
        by_tier[tier].append(err)
    return {
        tier: round(sum(vals) / len(vals), 3) if vals else 0.0
        for tier, vals in by_tier.items()
    }


def fit_stat_tier_bias_subtract(
    errors: List[Tuple[str, str, float]],
) -> Dict[str, Dict[str, float]]:
    """Fit per-stat tier subtract offsets."""
    buckets: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for stat, tier, err in errors:
        buckets[stat][tier].append(err)
    out: Dict[str, Dict[str, float]] = {}
    for stat, tiers in buckets.items():
        out[stat] = {
            tier: round(sum(vals) / len(vals), 3) if vals else 0.0
            for tier, vals in tiers.items()
        }
    return out


def apply_stat_tier_mean_bias_correction(
    mean: float,
    stat_type: str,
    *,
    tier: Optional[str] = None,
    stat_tier_offsets: Optional[Mapping[str, Mapping[str, float]]] = None,
) -> float:
    tier = tier or player_tier_for_bias(mean, stat_type)
    table = stat_tier_offsets or {}
    off = table.get(stat_type, {}).get(tier)
    if off is None:
        return apply_mean_bias_correction(mean, stat_type, tier=tier)
    corrected = mean - off
    return round(max(corrected, 0.0), 2)


def bias_report_from_errors(
    errors: List[Tuple[str, str, float]],
) -> Dict[str, Any]:
    """Summarize mean bias overall and by tier."""
    if not errors:
        return {"n": 0, "overall_mean_bias": None, "tier_mean_bias": {}}
    overall = sum(e[2] for e in errors) / len(errors)
    tier_vals: Dict[str, List[float]] = defaultdict(list)
    for _s, tier, err in errors:
        tier_vals[tier].append(err)
    tier_bias = {
        t: round(sum(v) / len(v), 3) for t, v in tier_vals.items() if v
    }
    return {
        "n": len(errors),
        "overall_mean_bias": round(overall, 3),
        "tier_mean_bias": tier_bias,
    }
