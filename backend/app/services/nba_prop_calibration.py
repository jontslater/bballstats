"""
Out-of-sample calibration for NBA player props with persisted gates.

Fit: season start through February. Test: March through season end.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.nba_prop_calibration_gate import NbaPropCalibrationGate
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

_PROP_GATE_CACHE: Dict[str, bool] = {}
_PROP_ADJUSTMENT_CACHE: Dict[str, float] = {}
_CACHE_LOADED = False

GATE_MAX_AGE_HOURS = 24


@dataclass
class PropCalibrationReport:
    stat_type: str
    brier: float
    median_line_p_over: float
    buckets: Dict[str, Dict[str, float]]
    passes_gate: bool
    prob_adjustment: float = 0.0


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


def apply_nba_probability_adjustment(stat_type: str, probability: float) -> float:
    adj = _PROP_ADJUSTMENT_CACHE.get(stat_type, 0.0)
    return max(0.001, min(0.999, probability - adj))


def _load_finished_nba_rows(db: Session, end_date: date, start_date: Optional[date] = None):
    q = (
        db.query(PlayerGameStat, Game)
        .join(Game, PlayerGameStat.game_id == Game.game_id)
        .filter(
            Game.sport == "NBA",
            Game.game_status == "finished",
            PlayerGameStat.sport == "NBA",
            Game.game_date <= end_date,
        )
    )
    if start_date:
        q = q.filter(Game.game_date >= start_date)
    return q.order_by(PlayerGameStat.player_id, Game.game_date).all()


def _build_player_histories(rows) -> Dict[int, List[Tuple[date, PlayerGameStat]]]:
    histories: Dict[int, List[Tuple[date, PlayerGameStat]]] = {}
    for stat_row, game in rows:
        histories.setdefault(stat_row.player_id, []).append((game.game_date, stat_row))
    return histories


def _rotation_minutes_from_history(history: List[Tuple[date, PlayerGameStat]], before_date: date, n: int = 10) -> float:
    mins = []
    for gdate, stat in reversed(history):
        if gdate >= before_date:
            continue
        if stat.minutes_played is not None:
            mins.append(stat.minutes_played)
        if len(mins) >= n:
            break
    if not mins:
        return 0.0
    return sum(mins) / len(mins)


def _predict_for_row(
    calc: CalibratedProbabilityCalculator,
    stat_type: str,
    history: List[Tuple[date, PlayerGameStat]],
    game_date: date,
    min_history: int,
    prob_adjustment: float,
) -> Optional[Tuple[float, float, int]]:
    hist_values = []
    for gdate, h_stat in history:
        if gdate >= game_date:
            continue
        v = _stat_value(h_stat, stat_type)
        if v is not None:
            hist_values.append(v)
    if len(hist_values) < min_history:
        return None
    hist_values = hist_values[-30:]
    mean = sum(hist_values) / len(hist_values)
    var = sum((x - mean) ** 2 for x in hist_values) / max(len(hist_values) - 1, 1)
    std = var ** 0.5
    line = _median_line_for_stat(hist_values)
    prob_data = calc.calculate_probability_for_line(
        line=line,
        player_mean=mean,
        player_std=std,
        sample_size=len(hist_values),
        stat_type=stat_type,
    )
    prob = float(prob_data["probability"])
    prob = max(0.001, min(0.999, prob - prob_adjustment))
    return prob, line, 1  # placeholder actual filled by caller


def _walk_forward_predictions(
    db: Session,
    stat_type: str,
    window_start: date,
    window_end: date,
    histories: Dict[int, List[Tuple[date, PlayerGameStat]]],
    prob_adjustment: float = 0.0,
    min_history: int = 10,
) -> List[Tuple[float, int, float]]:
    """Returns (probability, actual_hit, line) for each evaluation row."""
    calc = CalibratedProbabilityCalculator(sport="NBA")
    preds: List[Tuple[float, int, float]] = []

    for player_id, history in histories.items():
        for gdate, stat_row in history:
            if gdate < window_start or gdate > window_end:
                continue
            if _rotation_minutes_from_history(history, gdate) < 20:
                continue
            result = _predict_for_row(calc, stat_type, history, gdate, min_history, prob_adjustment)
            if not result:
                continue
            prob, line, _ = result
            actual = _stat_value(stat_row, stat_type)
            if actual is None:
                continue
            preds.append((prob, 1 if actual > line else 0, line))
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


def _median_line_p_over_all(predictions: List[Tuple[float, int, float]]) -> float:
    """Mean predicted P(over) across all rows at each row's median line (not filtered band)."""
    if not predictions:
        return 0.5
    return sum(p for p, _, _ in predictions) / len(predictions)


def _passes_gate(buckets: Dict[str, Dict[str, float]], median_line_p: float) -> bool:
    if not (0.45 <= median_line_p <= 0.55):
        return False
    for label in ("50-54", "55-59"):
        b = buckets.get(label, {})
        if b.get("n", 0) >= 25:
            if abs(b.get("predicted", 0) - b.get("actual", 0)) > 0.08:
                return False
    return True


def fit_prob_adjustment(predictions: List[Tuple[float, int, float]]) -> float:
    """Fit overshoot correction on 48–72% predicted band (early-season / fit window)."""
    band = [(p, a) for p, a, _ in predictions if 0.48 <= p <= 0.72]
    if len(band) < 40:
        return 0.0
    overshoot = sum(p - a for p, a in band) / len(band)
    return max(0.0, min(0.15, overshoot))


def evaluate_prop(
    db: Session,
    stat_type: str,
    test_start: date,
    test_end: date,
    histories: Dict[int, List[Tuple[date, PlayerGameStat]]],
    prob_adjustment: float,
) -> PropCalibrationReport:
    raw_preds = _walk_forward_predictions(
        db, stat_type, test_start, test_end, histories, prob_adjustment=prob_adjustment
    )
    pair_preds = [(p, a) for p, a, _ in raw_preds]
    buckets = _bucketize(pair_preds)
    median_line_p = _median_line_p_over_all(raw_preds)
    return PropCalibrationReport(
        stat_type=stat_type,
        brier=_brier(pair_preds),
        median_line_p_over=median_line_p,
        buckets=buckets,
        passes_gate=_passes_gate(buckets, median_line_p),
        prob_adjustment=prob_adjustment,
    )


def _season_windows(db: Session, season_year: str = "2025-26") -> Tuple[date, date, date]:
    from app.models.season import Season

    season_row = db.query(Season).filter(Season.sport == "NBA", Season.season_year == season_year).first()
    if season_row and season_row.start_date and season_row.end_date:
        fit_start = season_row.start_date
        fit_end = date(season_row.end_date.year, 2, 28)
        if season_row.start_date.year != season_row.end_date.year:
            fit_end = date(season_row.start_date.year + 1, 2, 28)
        test_start = date(fit_end.year, 3, 1)
        test_end = season_row.end_date
        return fit_start, test_start, test_end
    return date(2025, 10, 21), date(2026, 3, 1), date(2026, 6, 30)


def run_oos_calibration(db: Session, season_year: str = "2025-26") -> Dict[str, PropCalibrationReport]:
    fit_start, test_start, test_end = _season_windows(db, season_year)
    all_rows = _load_finished_nba_rows(db, test_end, start_date=fit_start)
    histories = _build_player_histories(all_rows)

    reports: Dict[str, PropCalibrationReport] = {}
    for stat in NBA_PROP_STATS:
        fit_preds = _walk_forward_predictions(
            db, stat, fit_start, test_start - timedelta(days=1), histories, prob_adjustment=0.0
        )
        adjustment = fit_prob_adjustment(fit_preds)
        reports[stat] = evaluate_prop(db, stat, test_start, test_end, histories, adjustment)
    return reports


def _persist_reports(db: Session, reports: Dict[str, PropCalibrationReport]) -> None:
    for stat, rep in reports.items():
        row = db.query(NbaPropCalibrationGate).filter(NbaPropCalibrationGate.stat_type == stat).first()
        if not row:
            row = NbaPropCalibrationGate(stat_type=stat)
            db.add(row)
        row.passes_gate = rep.passes_gate
        row.prob_adjustment = rep.prob_adjustment
        row.median_line_p_over = rep.median_line_p_over
        row.brier_score = rep.brier
        row.bucket_json = json.dumps(rep.buckets)
        row.updated_at = datetime.now(timezone.utc)
    db.commit()


def _load_from_db(db: Session) -> bool:
    global _PROP_GATE_CACHE, _PROP_ADJUSTMENT_CACHE, _CACHE_LOADED
    rows = db.query(NbaPropCalibrationGate).all()
    if not rows:
        _PROP_GATE_CACHE = {s: False for s in NBA_PROP_STATS}
        _PROP_ADJUSTMENT_CACHE = {s: 0.0 for s in NBA_PROP_STATS}
        _CACHE_LOADED = True
        return False
    _PROP_GATE_CACHE = {s: False for s in NBA_PROP_STATS}
    _PROP_ADJUSTMENT_CACHE = {s: 0.0 for s in NBA_PROP_STATS}
    for row in rows:
        _PROP_GATE_CACHE[row.stat_type] = bool(row.passes_gate)
        _PROP_ADJUSTMENT_CACHE[row.stat_type] = float(row.prob_adjustment or 0.0)
    _CACHE_LOADED = True
    return True


def _is_fresh(db: Session, max_age_hours: int) -> bool:
    latest = db.query(NbaPropCalibrationGate).order_by(NbaPropCalibrationGate.updated_at.desc()).first()
    if not latest or not latest.updated_at:
        return False
    updated = latest.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - updated < timedelta(hours=max_age_hours)


def load_prop_gates(db: Session, max_age_hours: int = GATE_MAX_AGE_HOURS) -> Dict[str, bool]:
    """Load persisted gates; recompute only when missing or stale."""
    global _CACHE_LOADED
    if _CACHE_LOADED and _PROP_GATE_CACHE and _is_fresh(db, max_age_hours):
        return _PROP_GATE_CACHE
    if _load_from_db(db) and _is_fresh(db, max_age_hours):
        return _PROP_GATE_CACHE
    return refresh_prop_gate_cache(db)


def refresh_prop_gate_cache(db: Session) -> Dict[str, PropCalibrationReport]:
    global _PROP_GATE_CACHE, _PROP_ADJUSTMENT_CACHE, _CACHE_LOADED
    reports = run_oos_calibration(db)
    _persist_reports(db, reports)
    _PROP_GATE_CACHE = {k: v.passes_gate for k, v in reports.items()}
    _PROP_ADJUSTMENT_CACHE = {k: v.prob_adjustment for k, v in reports.items()}
    for s in NBA_PROP_STATS:
        _PROP_GATE_CACHE.setdefault(s, False)
        _PROP_ADJUSTMENT_CACHE.setdefault(s, 0.0)
    _CACHE_LOADED = True
    return reports


def prop_passes_calibration_gate(stat_type: str, db: Optional[Session] = None) -> bool:
    if db is not None and not _CACHE_LOADED:
        load_prop_gates(db)
    return _PROP_GATE_CACHE.get(stat_type, False)
