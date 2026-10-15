"""
Statcast-based 'luck' adjustment for MLB hitter count-stat rate estimates.

Players whose actual results trail expected contact quality (xBA, xSLG, xwOBA)
get a modest upward rate nudge; overperformers are nudged down. Disabled by default
via MLB_LUCK_ADJUSTMENT until backtests justify enabling in production.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

MLB_LUCK_WEIGHT = float(os.environ.get("MLB_LUCK_WEIGHT", "0.35"))
MLB_LUCK_MIN_BIP = int(os.environ.get("MLB_LUCK_MIN_BIP", "25"))
MLB_LUCK_MAX_DELTA = float(os.environ.get("MLB_LUCK_MAX_DELTA", "0.12"))


def is_mlb_luck_adjustment_enabled() -> bool:
    return os.environ.get("MLB_LUCK_ADJUSTMENT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def luck_signal_for_stat(stat_type: str, metrics: Dict[str, float]) -> float:
    """
    Signed luck signal: positive => underperforming vs expected (due to regress up).

    Metrics are on batted balls in play (not per plate appearance).
    """
    ba = metrics.get("ba", 0.0)
    xba = metrics.get("xba", ba)
    slg = metrics.get("slg", 0.0)
    xslg = metrics.get("xslg", slg)
    woba = metrics.get("woba", 0.0)
    xwoba = metrics.get("xwoba", woba)

    if stat_type == "hits":
        return xba - ba
    if stat_type == "total_bases":
        return xslg - slg
    if stat_type == "home_runs":
        return xwoba - woba
    return 0.0


def apply_luck_to_mean(
    player_mean: float,
    stat_type: str,
    luck_metrics: Optional[Dict[str, Any]],
    *,
    enabled: Optional[bool] = None,
) -> Tuple[float, Dict[str, Any]]:
    """
    Blend luck signal into per-game mean before Poisson/NB calibration.

    Returns (adjusted_mean, debug_info).
    """
    debug: Dict[str, Any] = {"applied": False}
    if luck_metrics is None:
        return player_mean, debug

    bip = int(luck_metrics.get("bip") or 0)
    if bip < MLB_LUCK_MIN_BIP:
        debug["reason"] = "insufficient_bip"
        debug["bip"] = bip
        return player_mean, debug

    use_luck = is_mlb_luck_adjustment_enabled() if enabled is None else enabled
    if not use_luck:
        debug["reason"] = "disabled"
        return player_mean, debug

    signal = luck_signal_for_stat(stat_type, luck_metrics)
    confidence = min(1.0, bip / 80.0)
    raw_delta = MLB_LUCK_WEIGHT * signal * confidence
    delta = max(-MLB_LUCK_MAX_DELTA, min(MLB_LUCK_MAX_DELTA, raw_delta))
    adjusted = max(0.01, player_mean + delta)

    debug.update(
        {
            "applied": True,
            "bip": bip,
            "signal": round(signal, 4),
            "delta": round(delta, 4),
            "player_mean": round(player_mean, 4),
            "adjusted_mean": round(adjusted, 4),
        }
    )
    return adjusted, debug


def aggregate_daily_rows(rows) -> Dict[int, Dict[str, float]]:
    """Aggregate ORM daily rows into cumulative luck metrics keyed by mlbam_id."""
    totals: Dict[int, Dict[str, float]] = {}
    for row in rows:
        key = row.mlbam_id
        bucket = totals.setdefault(
            key,
            {
                "bip": 0,
                "hits_on_bip": 0,
                "total_bases_on_bip": 0,
                "sum_est_ba": 0.0,
                "sum_est_slg": 0.0,
                "sum_est_woba": 0.0,
                "hard_hit_count": 0,
                "barrel_count": 0,
            },
        )
        bucket["bip"] += row.bip or 0
        bucket["hits_on_bip"] += row.hits_on_bip or 0
        bucket["total_bases_on_bip"] += row.total_bases_on_bip or 0
        bucket["sum_est_ba"] += row.sum_est_ba or 0.0
        bucket["sum_est_slg"] += row.sum_est_slg or 0.0
        bucket["sum_est_woba"] += row.sum_est_woba or 0.0
        bucket["hard_hit_count"] += row.hard_hit_count or 0
        bucket["barrel_count"] += row.barrel_count or 0
    return totals


def metrics_from_totals(totals: Dict[str, float]) -> Optional[Dict[str, float]]:
    bip = int(totals.get("bip") or 0)
    if bip <= 0:
        return None
    hits = int(totals.get("hits_on_bip") or 0)
    tb = int(totals.get("total_bases_on_bip") or 0)
    return {
        "bip": bip,
        "ba": hits / bip,
        "xba": (totals.get("sum_est_ba") or 0.0) / bip,
        "slg": tb / bip,
        "xslg": (totals.get("sum_est_slg") or 0.0) / bip,
        "woba": (totals.get("sum_est_woba") or 0.0) / bip,
        "xwoba": (totals.get("sum_est_woba") or 0.0) / bip,
        "hard_hit_pct": (totals.get("hard_hit_count") or 0) / bip,
        "barrel_pct": (totals.get("barrel_count") or 0) / bip,
    }
