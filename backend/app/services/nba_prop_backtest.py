"""
Backtest / calibration report for NBA prop means and P(over) on finished games.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Game, Player, PlayerGameStat, Prediction, Season
from app.services.nba_sportsbook_edge import probability_over_line


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


def _player_tier(mean: float, stat_type: str) -> str:
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


@dataclass
class BacktestReport:
    season_year: str
    n_predictions: int = 0
    mean_error_sum: float = 0.0
    tier_mean_error: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))
    calibration_buckets: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        tier_bias = {
            tier: (sum(vals) / len(vals) if vals else None)
            for tier, vals in self.tier_mean_error.items()
        }
        cal = {}
        for bucket, counts in sorted(self.calibration_buckets.items()):
            n = counts.get("n", 0)
            hits = counts.get("hits", 0)
            cal[bucket] = {
                "n": n,
                "hit_rate": round(hits / n, 3) if n else None,
                "avg_predicted_p": round(counts.get("p_sum", 0) / n, 3) if n else None,
            }
        return {
            "season_year": self.season_year,
            "n_predictions": self.n_predictions,
            "overall_mean_bias": round(self.mean_error_sum / self.n_predictions, 3)
            if self.n_predictions
            else None,
            "tier_mean_bias": {k: (round(v, 3) if v is not None else None) for k, v in tier_bias.items()},
            "calibration": cal,
        }


def run_nba_prop_backtest(
    db: Session,
    season_year: str = "2025-26",
    *,
    stat_types: Optional[List[str]] = None,
) -> BacktestReport:
    stat_types = stat_types or ["points", "rebounds", "assists", "pts+ast+reb"]
    season = (
        db.query(Season)
        .filter(Season.sport == "NBA", Season.season_year == season_year)
        .first()
    )
    report = BacktestReport(season_year=season_year)
    if not season:
        return report

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

    for pred, _game, stat_row in preds:
        actual = _actual_stat(stat_row, pred.stat_type)
        if actual is None:
            continue
        mean = float(pred.distribution_mean)
        std = float(pred.distribution_std_dev or 0)
        line = float(pred.safe_line or mean)
        err = mean - actual
        report.n_predictions += 1
        report.mean_error_sum += err
        tier = _player_tier(mean, pred.stat_type)
        report.tier_mean_error[tier].append(err)

        p_over = probability_over_line(mean, std, line, stat_type=pred.stat_type)
        bucket = f"{int(p_over * 10) * 10}-{int(p_over * 10) * 10 + 10}%"
        b = report.calibration_buckets.setdefault(bucket, {"n": 0, "hits": 0, "p_sum": 0.0})
        b["n"] += 1
        b["p_sum"] += p_over
        if actual > line:
            b["hits"] += 1

    return report
