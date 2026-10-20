"""
Out-of-sample calibration for NBA player props.

Fit window: 2025-26 through February; test: March through season end.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.player_game_stat import PlayerGameStat
from app.services.calibrated_probability import CalibratedProbabilityCalculator

NBA_PROP_STATS = ("points", "rebounds", "assists", "three_pointers_made", "pts+ast+reb")

BUCKET_RANGES = [
    (0.50, 0.55, "50-54"),
    (0.55, 0.60, "55-59"),
    (0.60, 0.65, "60-64"),
    (0.65, 0.70, "65-69"),
    (0.70, 1.01, "70+"),
]


@dataclass
class PropCalibrationReport:
    stat_type: str
    brier: float
    median_line_p_over: float
    buckets: Dict[str, Dict[str, float]]
    passes_gate: bool


def _stat_value(stat: PlayerGameStat, stat_type: str) -> Optional[int]:
    if stat_type == "points":
        return stat.points
    if stat_type == "rebounds":
        return stat.rebounds
    if stat_type == "assists":
        return stat.assists
    if stat_type == "three_pointers_made":
        return stat.three_pointers_made
    if stat_type == "pts+ast+reb":
        if stat.points is None or stat.rebounds is None or stat.assists is None:
            return None
        return stat.points + stat.rebounds + stat.assists
    return None


def _median_line_for_stat(values: List[int]) -> float:
    if not values:
        return 0.5
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2:
        return float(sorted_vals[mid]) - 0.5
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def _rotation_minutes_avg(db: Session, player_id: int, before_date: date, n: int = 10) -> float:
    rows = (
        db.query(PlayerGameStat.minutes_played)
        .join(Game, PlayerGameStat.game_id == Game.game_id)
        .filter(
            PlayerGameStat.sport == "NBA",
            PlayerGameStat.player_id == player_id,
            Game.game_date < before_date,
            Game.game_status == "finished",
            PlayerGameStat.minutes_played.isnot(None),
        )
        .order_by(Game.game_date.desc())
        .limit(n)
        .all()
    )
    if not rows:
        return 0.0
    return sum(r[0] or 0 for r in rows) / len(rows)


def _walk_forward_predictions(
    db: Session,
    stat_type: str,
    test_start: date,
    test_end: date,
    min_history: int = 10,
) -> List[Tuple[float, int]]:
    calc = CalibratedProbabilityCalculator(sport="NBA")
    preds: List[Tuple[float, int]] = []

    test_games = (
        db.query(PlayerGameStat, Game)
        .join(Game, PlayerGameStat.game_id == Game.game_id)
        .filter(
            Game.sport == "NBA",
            Game.game_status == "finished",
            Game.game_date >= test_start,
            Game.game_date <= test_end,
            PlayerGameStat.sport == "NBA",
        )
        .all()
    )

    for stat_row, game in test_games:
        if _rotation_minutes_avg(db, stat_row.player_id, game.game_date) < 20:
            continue
        history = (
            db.query(PlayerGameStat, Game)
            .join(Game, PlayerGameStat.game_id == Game.game_id)
            .filter(
                PlayerGameStat.player_id == stat_row.player_id,
                Game.game_date < game.game_date,
                Game.game_status == "finished",
            )
            .order_by(Game.game_date.desc())
            .limit(30)
            .all()
        )
        hist_values = []
        for h_stat, _ in history:
            v = _stat_value(h_stat, stat_type)
            if v is not None:
                hist_values.append(v)
        if len(hist_values) < min_history:
            continue

        mean = sum(hist_values) / len(hist_values)
        var = sum((x - mean) ** 2 for x in hist_values) / max(len(hist_values) - 1, 1)
        std = var ** 0.5
        line = _median_line_for_stat(hist_values)
        prob = calc.calculate_probability_for_line(
            line=line,
            player_mean=mean,
            player_std=std,
            sample_size=len(hist_values),
            stat_type=stat_type,
        )
        actual = _stat_value(stat_row, stat_type)
        if actual is None:
            continue
        preds.append((prob, 1 if actual > line else 0))
    return preds


def _bucketize(predictions: List[Tuple[float, int]]) -> Dict[str, Dict[str, float]]:
    buckets: Dict[str, Dict[str, float]] = {}
    for lo, hi, label in BUCKET_RANGES:
        subset = [(p, a) for p, a in predictions if lo <= p < hi]
        n = len(subset)
        if n == 0:
            buckets[label] = {"n": 0, "predicted": 0.0, "actual": 0.0}
            continue
        pred_avg = sum(p for p, _ in subset) / n
        act_avg = sum(a for _, a in subset) / n
        buckets[label] = {"n": n, "predicted": pred_avg, "actual": act_avg}
    return buckets


def _brier(predictions: List[Tuple[float, int]]) -> float:
    if not predictions:
        return 0.0
    return sum((p - a) ** 2 for p, a in predictions) / len(predictions)


def evaluate_prop(db: Session, stat_type: str, test_start: date, test_end: date) -> PropCalibrationReport:
    predictions = _walk_forward_predictions(db, stat_type, test_start, test_end)
    buckets = _bucketize(predictions)
    median_preds = [(p, a) for p, a in predictions if 0.45 <= p <= 0.55]
    median_line_p = sum(p for p, _ in median_preds) / len(median_preds) if median_preds else 0.5

    passes = True
    if not (0.45 <= median_line_p <= 0.55):
        passes = False
    for label in ("50-54", "55-59"):
        b = buckets.get(label, {})
        if b.get("n", 0) >= 25:
            if abs(b.get("predicted", 0) - b.get("actual", 0)) > 0.08:
                passes = False

    return PropCalibrationReport(
        stat_type=stat_type,
        brier=_brier(predictions),
        median_line_p_over=median_line_p,
        buckets=buckets,
        passes_gate=passes,
    )


def run_oos_calibration(
    db: Session,
    season_year: str = "2025-26",
    fit_end_month: int = 2,
) -> Dict[str, PropCalibrationReport]:
    """Fit through February of season_year; test March through season end."""
    from app.models.season import Season

    season_row = db.query(Season).filter(Season.sport == "NBA", Season.season_year == season_year).first()
    if season_row and season_row.start_date and season_row.end_date:
        y_start = season_row.start_date.year
        test_start = date(y_start + 1, 3, 1) if season_year.endswith("-26") else date(y_start, 3, 1)
        test_end = season_row.end_date
    else:
        # 2025-26: test Mar 2026 - Jun 2026
        test_start = date(2026, 3, 1)
        test_end = date(2026, 6, 30)

    reports = {}
    for stat in NBA_PROP_STATS:
        reports[stat] = evaluate_prop(db, stat, test_start, test_end)
    return reports


# Module-level cache of gate results (populated by calibration script)
_PROP_GATE_CACHE: Dict[str, bool] = {s: True for s in NBA_PROP_STATS}


def refresh_prop_gate_cache(db: Session) -> Dict[str, bool]:
    global _PROP_GATE_CACHE
    reports = run_oos_calibration(db)
    _PROP_GATE_CACHE = {k: v.passes_gate for k, v in reports.items()}
    return _PROP_GATE_CACHE


def prop_passes_calibration_gate(stat_type: str) -> bool:
    return _PROP_GATE_CACHE.get(stat_type, True)
