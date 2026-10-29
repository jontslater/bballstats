"""
Backtest / calibration report for NBA prop means and P(over).

Uses saved predictions when present; otherwise point-in-time on-the-fly generation.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Game, PlayerGameStat, Prediction, Season
from app.services.nba_mean_bias_correction import (
    apply_mean_bias_correction,
    bias_report_from_errors,
    fit_tier_bias_subtract,
    player_tier_for_bias,
)
from app.services.nba_sportsbook_edge import find_sportsbook_line, probability_over_line
from app.services.prediction_service import PredictionService


def _actual_stat(stat_row: PlayerGameStat, stat_type: str) -> Optional[float]:
    if stat_type == "points":
        return float(stat_row.points or 0)
    if stat_type == "rebounds":
        return float(stat_row.rebounds or 0)
    if stat_type == "assists":
        return float(stat_row.assists or 0)
    if stat_type == "three_pointers_made":
        return float(stat_row.three_pointers_made or 0)
    if stat_type == "pts+ast+reb":
        return float((stat_row.points or 0) + (stat_row.rebounds or 0) + (stat_row.assists or 0))
    return None


def rolling_median_proxy_line(
    db: Session,
    player_id: int,
    stat_type: str,
    before_date: date,
    *,
    window: int = 20,
    season_ids: Optional[List[int]] = None,
) -> Optional[float]:
    q = (
        db.query(PlayerGameStat, Game)
        .join(Game, Game.game_id == PlayerGameStat.game_id)
        .filter(
            PlayerGameStat.player_id == player_id,
            PlayerGameStat.sport == "NBA",
            Game.game_status == "finished",
            Game.game_date < before_date,
            PlayerGameStat.minutes_played > 0,
        )
        .order_by(Game.game_date.desc())
    )
    if season_ids:
        q = q.filter(Game.season_id.in_(season_ids))
    values: List[float] = []
    for stat_row, _g in q.limit(window).all():
        v = _actual_stat(stat_row, stat_type)
        if v is not None:
            values.append(v)
    if len(values) < 3:
        return None
    return float(median(values))


def _add_cal_bucket(
    table: Dict[str, Dict[str, float]],
    mean: float,
    std: float,
    line: float,
    actual: float,
    stat_type: str,
) -> None:
    p_over = probability_over_line(mean, std, line, stat_type=stat_type)
    bucket = f"{int(p_over * 10) * 10}-{int(p_over * 10) * 10 + 10}%"
    row = table.setdefault(bucket, {"n": 0, "hits": 0, "p_sum": 0.0})
    row["n"] += 1
    row["p_sum"] += p_over
    if actual > line:
        row["hits"] += 1


@dataclass
class BacktestReport:
    season_year: str
    mode: str = "saved"
    n_predictions: int = 0
    mean_error_sum: float = 0.0
    tier_mean_error: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))
    calibration_median: Dict[str, Dict[str, float]] = field(default_factory=dict)
    calibration_book: Dict[str, Dict[str, float]] = field(default_factory=dict)
    raw_errors: List[Tuple[str, str, float]] = field(default_factory=list)
    fitted_tier_subtract: Dict[str, float] = field(default_factory=dict)
    bias_after_fitted_correction: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        tier_bias = {
            tier: (sum(vals) / len(vals) if vals else None)
            for tier, vals in self.tier_mean_error.items()
        }

        def _cal_table(src: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
            out = {}
            for bucket, counts in sorted(src.items()):
                n = int(counts.get("n", 0))
                hits = int(counts.get("hits", 0))
                out[bucket] = {
                    "n": n,
                    "hit_rate": round(hits / n, 3) if n else None,
                    "avg_predicted_p": round(counts.get("p_sum", 0) / n, 3) if n else None,
                }
            return out

        return {
            "season_year": self.season_year,
            "mode": self.mode,
            "n_predictions": self.n_predictions,
            "overall_mean_bias": round(self.mean_error_sum / self.n_predictions, 3)
            if self.n_predictions
            else None,
            "tier_mean_bias": {
                k: (round(v, 3) if v is not None else None) for k, v in tier_bias.items()
            },
            "calibration_median_line": _cal_table(self.calibration_median),
            "calibration_book_line": _cal_table(self.calibration_book),
            "fitted_tier_subtract": self.fitted_tier_subtract,
            "bias_after_fitted_correction": self.bias_after_fitted_correction,
        }


def _score_row(
    report: BacktestReport,
    db: Session,
    *,
    game_id: int,
    player_id: int,
    game_date: date,
    stat_type: str,
    mean: float,
    std: float,
    actual: float,
    season_ids: List[int],
) -> None:
    err = mean - actual
    report.n_predictions += 1
    report.mean_error_sum += err
    tier = player_tier_for_bias(mean, stat_type)
    report.tier_mean_error[tier].append(err)
    report.raw_errors.append((stat_type, tier, err))

    proxy = rolling_median_proxy_line(
        db, player_id, stat_type, game_date, season_ids=season_ids
    )
    if proxy is not None:
        _add_cal_bucket(report.calibration_median, mean, std, proxy, actual, stat_type)

    book = find_sportsbook_line(db, game_id, player_id, stat_type)
    if book and book.over_line is not None:
        _add_cal_bucket(
            report.calibration_book,
            mean,
            std,
            float(book.over_line),
            actual,
            stat_type,
        )


def _finalize_report(report: BacktestReport) -> BacktestReport:
    report.fitted_tier_subtract = fit_tier_bias_subtract(report.raw_errors)
    corrected: List[Tuple[str, str, float]] = []
    for stat_type, tier, err in report.raw_errors:
        off = report.fitted_tier_subtract.get(tier, 0.0)
        from app.services.nba_mean_bias_correction import STAT_TIER_SCALE

        corrected.append((stat_type, tier, err - off * STAT_TIER_SCALE.get(stat_type, 0.5)))
    report.bias_after_fitted_correction = bias_report_from_errors(corrected)
    return report


def _run_saved_prediction_backtest(
    db: Session,
    season: Season,
    stat_types: List[str],
) -> BacktestReport:
    report = BacktestReport(season_year=season.season_year, mode="saved")
    preds = (
        db.query(Prediction, Game, PlayerGameStat)
        .join(Game, Game.game_id == Prediction.game_id)
        .join(
            PlayerGameStat,
            (PlayerGameStat.game_id == Prediction.game_id)
            & (PlayerGameStat.player_id == Prediction.player_id),
        )
        .filter(
            Prediction.sport == "NBA",
            Game.season_id == season.season_id,
            Game.game_status == "finished",
            Prediction.bet_type == "safe",
            Prediction.stat_type.in_(stat_types),
            Prediction.distribution_mean.isnot(None),
        )
        .all()
    )
    season_ids = [season.season_id]
    for pred, game, stat_row in preds:
        actual = _actual_stat(stat_row, pred.stat_type)
        if actual is None:
            continue
        mean = float(pred.distribution_mean)
        std = float(pred.distribution_std_dev or 1.0)
        _score_row(
            report,
            db,
            game_id=game.game_id,
            player_id=pred.player_id,
            game_date=game.game_date,
            stat_type=pred.stat_type,
            mean=mean,
            std=std,
            actual=actual,
            season_ids=season_ids,
        )
    return _finalize_report(report)


def _run_pit_backtest(
    db: Session,
    season: Season,
    stat_types: List[str],
    *,
    max_samples: Optional[int] = None,
) -> BacktestReport:
    from app.services.nba_season_blend import prior_nba_season_id

    report = BacktestReport(season_year=season.season_year, mode="pit")
    svc = PredictionService(db, sport="NBA")
    season_ids = [season.season_id]
    prior_id = prior_nba_season_id(db, season.season_id)
    if prior_id:
        season_ids.append(prior_id)

    games = (
        db.query(Game)
        .filter(
            Game.season_id == season.season_id,
            Game.sport == "NBA",
            Game.game_status == "finished",
        )
        .order_by(Game.game_date)
        .all()
    )

    samples = 0
    for game in games:
        stats = (
            db.query(PlayerGameStat)
            .filter(
                PlayerGameStat.game_id == game.game_id,
                PlayerGameStat.sport == "NBA",
                PlayerGameStat.minutes_played >= 12,
            )
            .all()
        )
        for stat_row in stats:
            for stat_type in stat_types:
                actual = _actual_stat(stat_row, stat_type)
                if actual is None:
                    continue
                pred = svc.generate_prediction(
                    stat_row.player_id,
                    game.game_id,
                    stat_type,
                    pit_mode=True,
                    as_of_date=game.game_date,
                    persist=False,
                    apply_bias_correction=False,
                )
                if pred is None or pred.distribution_mean is None:
                    continue
                mean = float(pred.distribution_mean)
                std = float(pred.distribution_std_dev or 1.0)
                _score_row(
                    report,
                    db,
                    game_id=game.game_id,
                    player_id=stat_row.player_id,
                    game_date=game.game_date,
                    stat_type=stat_type,
                    mean=mean,
                    std=std,
                    actual=actual,
                    season_ids=season_ids,
                )
                samples += 1
                if max_samples and samples >= max_samples:
                    return _finalize_report(report)

    return _finalize_report(report)


def run_nba_prop_backtest(
    db: Session,
    season_year: str = "2025-26",
    *,
    stat_types: Optional[List[str]] = None,
    pit: Optional[bool] = None,
    max_samples: Optional[int] = None,
) -> BacktestReport:
    stat_types = stat_types or ["points", "rebounds", "assists", "pts+ast+reb"]
    season = (
        db.query(Season)
        .filter(Season.sport == "NBA", Season.season_year == season_year)
        .first()
    )
    if not season:
        return BacktestReport(season_year=season_year)

    saved_count = (
        db.query(Prediction)
        .join(Game, Game.game_id == Prediction.game_id)
        .filter(
            Prediction.sport == "NBA",
            Game.season_id == season.season_id,
            Game.game_status == "finished",
            Prediction.bet_type == "safe",
            Prediction.stat_type.in_(stat_types),
        )
        .count()
    )

    use_pit = pit if pit is not None else saved_count == 0
    if use_pit:
        return _run_pit_backtest(db, season, stat_types, max_samples=max_samples)
    return _run_saved_prediction_backtest(db, season, stat_types)


def graded_prediction_bias_report(
    db: Session,
    season_year: str = "2026-27",
    *,
    stat_types: Optional[List[str]] = None,
    date_start: Optional[date] = None,
    date_end: Optional[date] = None,
) -> Dict[str, Any]:
    stat_types = stat_types or ["points", "rebounds", "assists", "pts+ast+reb"]
    season = (
        db.query(Season)
        .filter(Season.sport == "NBA", Season.season_year == season_year)
        .first()
    )
    if not season:
        return {"before_correction": {"n": 0}, "after_correction": {"n": 0}}

    q = (
        db.query(Prediction, PlayerGameStat)
        .join(Game, Game.game_id == Prediction.game_id)
        .join(
            PlayerGameStat,
            (PlayerGameStat.game_id == Prediction.game_id)
            & (PlayerGameStat.player_id == Prediction.player_id),
        )
        .filter(
            Prediction.sport == "NBA",
            Game.season_id == season.season_id,
            Game.game_status == "finished",
            Prediction.bet_type == "safe",
            Prediction.stat_type.in_(stat_types),
            Prediction.distribution_mean.isnot(None),
        )
    )
    if date_start:
        q = q.filter(Game.game_date >= date_start)
    if date_end:
        q = q.filter(Game.game_date <= date_end)

    before: List[Tuple[str, str, float]] = []
    after: List[Tuple[str, str, float]] = []
    for pred, stat_row in q.all():
        actual = _actual_stat(stat_row, pred.stat_type)
        if actual is None:
            continue
        raw_mean = float(pred.distribution_mean)
        tier = player_tier_for_bias(raw_mean, pred.stat_type)
        before.append((pred.stat_type, tier, raw_mean - actual))
        corr_mean = apply_mean_bias_correction(raw_mean, pred.stat_type, tier=tier)
        after.append(
            (pred.stat_type, player_tier_for_bias(corr_mean, pred.stat_type), corr_mean - actual)
        )

    return {
        "before_correction": bias_report_from_errors(before),
        "after_correction": bias_report_from_errors(after),
    }
