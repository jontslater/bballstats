"""
Backtest / calibration report for NBA prop means and P(over).

Uses saved predictions when present; otherwise point-in-time on-the-fly generation
with stratified sampling and cached player logs.
"""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models import Game, PlayerGameStat, Prediction, Season
from app.services.nba_mean_bias_correction import (
    apply_mean_bias_correction,
    bias_report_from_errors,
    fit_shrunk_tier_subtract,
    player_tier_for_bias,
    STAT_TIER_SCALE,
)
from app.services.nba_prop_calibration_store import (
    get_prob_shrink,
    get_tier_subtract_offsets,
    save_calibration,
)
from app.services.nba_prop_player_cache import (
    PitCandidate,
    PlayerStatHistoryCache,
    stat_value_from_row,
)
from app.services.nba_prop_prob_fit import collect_prob_samples, fit_prob_shrink_brier
from app.services.nba_sportsbook_edge import find_sportsbook_line, probability_over_line
from app.services.prediction_service import PredictionService


def _add_cal_bucket(
    table: Dict[str, Dict[str, float]],
    mean: float,
    std: float,
    line: float,
    actual: float,
    stat_type: str,
    *,
    calibrate: bool = True,
    prob_shrink: Optional[float] = None,
) -> None:
    p_over = probability_over_line(
        mean,
        std,
        line,
        stat_type=stat_type,
        calibrate=calibrate,
        prob_shrink=prob_shrink,
    )
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
    prob_shrink_used: Optional[float] = None
    sample_count_requested: Optional[int] = None
    sample_count_used: Optional[int] = None

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
            "prob_shrink_used": self.prob_shrink_used,
            "sample_count_requested": self.sample_count_requested,
            "sample_count_used": self.sample_count_used,
        }


def build_pit_candidates(
    db: Session,
    season: Season,
    stat_types: Sequence[str],
    cache: PlayerStatHistoryCache,
    *,
    min_minutes: float = 12.0,
) -> List[PitCandidate]:
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
    game_ids = [g.game_id for g in games]
    if not game_ids:
        return []
    stats = (
        db.query(PlayerGameStat, Game)
        .join(Game, Game.game_id == PlayerGameStat.game_id)
        .filter(
            PlayerGameStat.game_id.in_(game_ids),
            PlayerGameStat.sport == "NBA",
            PlayerGameStat.minutes_played >= min_minutes,
        )
        .all()
    )
    candidates: List[PitCandidate] = []
    for stat_row, game in stats:
        for stat_type in stat_types:
            actual = stat_value_from_row(stat_row, stat_type)
            if actual is None:
                continue
            if cache.rolling_median(stat_row.player_id, stat_type, game.game_date) is None:
                continue
            candidates.append(
                PitCandidate(
                    game_id=game.game_id,
                    player_id=stat_row.player_id,
                    stat_type=stat_type,
                    game_date=game.game_date,
                    actual=float(actual),
                )
            )
    return candidates


def sample_candidates(
    candidates: List[PitCandidate],
    max_samples: Optional[int],
    *,
    seed: int = 42,
    strategy: str = "random",
) -> List[PitCandidate]:
    if not max_samples or len(candidates) <= max_samples:
        return candidates
    if strategy == "stride":
        step = max(1, len(candidates) // max_samples)
        picked = candidates[::step][:max_samples]
        return picked
    rng = random.Random(seed)
    return rng.sample(candidates, max_samples)


def _score_pit_row(
    report: BacktestReport,
    *,
    mean: float,
    std: float,
    candidate: PitCandidate,
    cache: PlayerStatHistoryCache,
    db: Session,
    tier_subtract: Optional[Dict[str, float]],
    calibrate: bool,
    prob_shrink: Optional[float],
) -> None:
    err = mean - candidate.actual
    report.n_predictions += 1
    report.mean_error_sum += err
    tier = player_tier_for_bias(mean, candidate.stat_type)
    report.tier_mean_error[tier].append(err)
    report.raw_errors.append((candidate.stat_type, tier, err))

    proxy = cache.rolling_median(
        candidate.player_id, candidate.stat_type, candidate.game_date
    )
    if proxy is not None:
        _add_cal_bucket(
            report.calibration_median,
            mean,
            std,
            proxy,
            candidate.actual,
            candidate.stat_type,
            calibrate=calibrate,
            prob_shrink=prob_shrink,
        )

    book = find_sportsbook_line(
        db, candidate.game_id, candidate.player_id, candidate.stat_type
    )
    if book and book.over_line is not None:
        _add_cal_bucket(
            report.calibration_book,
            mean,
            std,
            float(book.over_line),
            candidate.actual,
            candidate.stat_type,
            calibrate=calibrate,
            prob_shrink=prob_shrink,
        )


def _run_pit_backtest(
    db: Session,
    season: Season,
    stat_types: List[str],
    *,
    max_samples: Optional[int] = None,
    seed: int = 42,
    sample_strategy: str = "random",
    apply_tier_subtract: bool = False,
    tier_subtract: Optional[Dict[str, float]] = None,
    calibrate_prob: bool = True,
    prob_shrink: Optional[float] = None,
) -> BacktestReport:
    from app.services.nba_season_blend import prior_nba_season_id

    report = BacktestReport(season_year=season.season_year, mode="pit")
    report.sample_count_requested = max_samples
    svc = PredictionService(db, sport="NBA")
    season_ids = [season.season_id]
    prior_id = prior_nba_season_id(db, season.season_id)
    if prior_id:
        season_ids.append(prior_id)

    cache = PlayerStatHistoryCache(db, season_ids)
    candidates = build_pit_candidates(db, season, stat_types, cache)
    picked = sample_candidates(
        candidates, max_samples, seed=seed, strategy=sample_strategy
    )
    report.sample_count_used = len(picked)

    offsets = tier_subtract
    if apply_tier_subtract and offsets is None:
        offsets = get_tier_subtract_offsets()
    if not offsets:
        offsets = None

    shrink = prob_shrink if prob_shrink is not None else get_prob_shrink()
    report.prob_shrink_used = shrink if calibrate_prob else 1.0

    for candidate in picked:
        pred = svc.generate_prediction(
            candidate.player_id,
            candidate.game_id,
            candidate.stat_type,
            pit_mode=True,
            as_of_date=candidate.game_date,
            persist=False,
            apply_bias_correction=False,
        )
        if pred is None or pred.distribution_mean is None:
            continue
        mean = float(pred.distribution_mean)
        if offsets:
            mean = apply_mean_bias_correction(
                mean, candidate.stat_type, offsets=offsets
            )
        std = float(pred.distribution_std_dev or 1.0)
        _score_pit_row(
            report,
            mean=mean,
            std=std,
            candidate=candidate,
            cache=cache,
            db=db,
            tier_subtract=offsets,
            calibrate=calibrate_prob,
            prob_shrink=shrink if calibrate_prob else 1.0,
        )

    report.fitted_tier_subtract = fit_shrunk_tier_subtract(report.raw_errors)
    return report


def fit_and_save_calibration(
    db: Session,
    *,
    train_season: str = "2025-26",
    stat_types: Optional[List[str]] = None,
    max_samples: int = 400,
    seed: int = 42,
    sample_strategy: str = "random",
    per_tier_cap: float = 2.0,
) -> Dict[str, Any]:
    stat_types = stat_types or ["points", "rebounds", "assists", "pts+ast+reb"]
    train = _run_pit_backtest(
        db,
        _require_season(db, train_season),
        stat_types,
        max_samples=max_samples,
        seed=seed,
        sample_strategy=sample_strategy,
        apply_tier_subtract=False,
        calibrate_prob=False,
    )
    tier_sub = fit_shrunk_tier_subtract(
        train.raw_errors, per_tier_cap=per_tier_cap
    )
    prob_rows: List[Tuple[float, float, float, str, float]] = []
    season = _require_season(db, train_season)
    season_ids = [season.season_id]
    from app.services.nba_season_blend import prior_nba_season_id

    prior_id = prior_nba_season_id(db, season.season_id)
    if prior_id:
        season_ids.append(prior_id)
    cache = PlayerStatHistoryCache(db, season_ids)
    svc = PredictionService(db, sport="NBA")
    candidates = sample_candidates(
        build_pit_candidates(db, season, stat_types, cache),
        max_samples,
        seed=seed,
        strategy=sample_strategy,
    )
    for c in candidates:
        pred = svc.generate_prediction(
            c.player_id,
            c.game_id,
            c.stat_type,
            pit_mode=True,
            as_of_date=c.game_date,
            persist=False,
            apply_bias_correction=False,
        )
        if pred is None or pred.distribution_mean is None:
            continue
        mean = float(pred.distribution_mean)
        if tier_sub:
            mean = apply_mean_bias_correction(mean, c.stat_type, offsets=tier_sub)
        proxy = cache.rolling_median(c.player_id, c.stat_type, c.game_date)
        if proxy is None:
            continue
        prob_rows.append(
            (
                mean,
                float(pred.distribution_std_dev or 1.0),
                proxy,
                c.stat_type,
                c.actual,
            )
        )
    prob_shrink = fit_prob_shrink_brier(collect_prob_samples(prob_rows))
    save_calibration(
        {
            "fit_season": train_season,
            "tier_subtract": tier_sub,
            "prob_shrink": prob_shrink,
        }
    )
    return {
        "train_bias": train.to_dict(),
        "tier_subtract_saved": tier_sub,
        "prob_shrink_saved": prob_shrink,
    }


def validate_calibration(
    db: Session,
    *,
    season_year: str = "2026-27",
    stat_types: Optional[List[str]] = None,
    max_samples: int = 400,
    seed: int = 42,
    sample_strategy: str = "random",
) -> Dict[str, Any]:
    stat_types = stat_types or ["points", "rebounds", "assists", "pts+ast+reb"]
    report = _run_pit_backtest(
        db,
        _require_season(db, season_year),
        stat_types,
        max_samples=max_samples,
        seed=seed,
        sample_strategy=sample_strategy,
        apply_tier_subtract=True,
        calibrate_prob=True,
    )
    return report.to_dict()


def _require_season(db: Session, season_year: str) -> Season:
    season = (
        db.query(Season)
        .filter(Season.sport == "NBA", Season.season_year == season_year)
        .first()
    )
    if not season:
        raise ValueError(f"Season not found: {season_year}")
    return season


def run_nba_prop_backtest(
    db: Session,
    season_year: str = "2025-26",
    *,
    stat_types: Optional[List[str]] = None,
    pit: Optional[bool] = None,
    max_samples: Optional[int] = None,
    seed: int = 42,
    sample_strategy: str = "random",
    apply_tier_subtract: bool = False,
    calibrate_prob: bool = True,
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
        return _run_pit_backtest(
            db,
            season,
            stat_types,
            max_samples=max_samples,
            seed=seed,
            sample_strategy=sample_strategy,
            apply_tier_subtract=apply_tier_subtract,
            calibrate_prob=calibrate_prob,
        )
    return _run_saved_backtest(db, season, stat_types, calibrate_prob=calibrate_prob)


def _run_saved_backtest(
    db: Session,
    season: Season,
    stat_types: List[str],
    *,
    calibrate_prob: bool,
) -> BacktestReport:
    report = BacktestReport(season_year=season.season_year, mode="saved")
    cache = PlayerStatHistoryCache(db, [season.season_id])
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
    shrink = get_prob_shrink() if calibrate_prob else 1.0
    report.prob_shrink_used = shrink
    for pred, game, stat_row in preds:
        actual = stat_value_from_row(stat_row, pred.stat_type)
        if actual is None:
            continue
        mean = float(pred.distribution_mean)
        std = float(pred.distribution_std_dev or 1.0)
        cand = PitCandidate(
            game.game_id,
            pred.player_id,
            pred.stat_type,
            game.game_date,
            float(actual),
        )
        _score_pit_row(
            report,
            mean=mean,
            std=std,
            candidate=cand,
            cache=cache,
            db=db,
            tier_subtract=None,
            calibrate=calibrate_prob,
            prob_shrink=shrink,
        )
    report.fitted_tier_subtract = fit_shrunk_tier_subtract(report.raw_errors)
    return report


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
        return {"minutes_only": {"n": 0}, "with_saved_subtract": {"n": 0}}

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

    raw_errors: List[Tuple[str, str, float]] = []
    offsets = get_tier_subtract_offsets()
    corrected: List[Tuple[str, str, float]] = []
    for pred, stat_row in q.all():
        actual = stat_value_from_row(stat_row, pred.stat_type)
        if actual is None:
            continue
        raw_mean = float(pred.distribution_mean)
        tier = player_tier_for_bias(raw_mean, pred.stat_type)
        raw_errors.append((pred.stat_type, tier, raw_mean - actual))
        if offsets:
            corr = apply_mean_bias_correction(raw_mean, pred.stat_type, offsets=offsets)
            corrected.append(
                (
                    pred.stat_type,
                    player_tier_for_bias(corr, pred.stat_type),
                    corr - actual,
                )
            )

    out: Dict[str, Any] = {"minutes_only": bias_report_from_errors(raw_errors)}
    if offsets:
        out["with_saved_subtract"] = bias_report_from_errors(corrected)
    else:
        out["with_saved_subtract"] = {"n": 0, "note": "no tier_subtract in calibration file"}
    return out
