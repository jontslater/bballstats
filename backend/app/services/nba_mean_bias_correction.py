"""
Per-stat / tier mean bias correction for NBA prop predictions.

Production subtract offsets come from PIT-fit calibration JSON only (no hard-coded defaults).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Tuple

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
    """Subtract fitted tier bias (optionally scaled by stat type). No-op when offsets empty."""
    if mean is None:
        return mean
    offsets = offsets or {}
    if not offsets:
        return round(float(mean), 2)
    tier = tier or player_tier_for_bias(mean, stat_type)
    base = float(offsets.get(tier, 0.0))
    if base == 0.0:
        return round(float(mean), 2)
    scale = STAT_TIER_SCALE.get(stat_type, 0.5)
    corrected = mean - base * scale
    return round(max(corrected, 0.0), 2)


def fit_tier_bias_subtract(
    errors: List[Tuple[str, str, float]],
) -> Dict[str, float]:
    by_tier: Dict[str, List[float]] = defaultdict(list)
    for _stat, tier, err in errors:
        by_tier[tier].append(err)
    return {
        tier: round(sum(vals) / len(vals), 3) if vals else 0.0
        for tier, vals in by_tier.items()
    }


def fit_shrunk_tier_subtract(
    errors: List[Tuple[str, str, float]],
    *,
    per_tier_cap: float = 2.0,
    shrink_prior_n: float = 40.0,
) -> Dict[str, float]:
    """
    Fit tier subtract amounts with cap and shrinkage toward zero.
    error = model_mean - actual (positive => subtract from mean).
    """
    by_tier: Dict[str, List[float]] = defaultdict(list)
    for _stat, tier, err in errors:
        by_tier[tier].append(err)
    out: Dict[str, float] = {}
    cap = max(0.5, float(per_tier_cap))
    for tier, vals in by_tier.items():
        if not vals:
            continue
        raw = sum(vals) / len(vals)
        w = len(vals) / (len(vals) + shrink_prior_n)
        shrunk = raw * w
        if shrunk > cap:
            shrunk = cap
        elif shrunk < -cap:
            shrunk = -cap
        if abs(shrunk) < 0.05:
            shrunk = 0.0
        out[tier] = round(shrunk, 3)
    return out


def bias_report_from_errors(
    errors: List[Tuple[str, str, float]],
) -> Dict[str, Any]:
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
