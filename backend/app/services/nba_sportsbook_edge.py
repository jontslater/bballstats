"""
NBA sportsbook line matching and edge math for suggested bets.
"""
from __future__ import annotations

from typing import Optional

from scipy.stats import norm
from sqlalchemy.orm import Session

from app.models.betting_line import BettingLine

BOOKMAKER_PREFERENCE = ("FanDuel", "DraftKings")

PROB_CLAMP_LOW = 0.05
PROB_CLAMP_HIGH = 0.90
MAX_PROB_EDGE = 0.10  # skip p - breakeven above this (overconfident / bad sigma)

# Max |model mean − book line| before treating as misaligned data.
STAT_MEAN_BOOK_GAP: dict[str, float] = {
    "points": 4.0,
    "rebounds": 2.5,
    "assists": 2.5,
    "three_pointers_made": 1.5,
    "pts+ast+reb": 4.0,
}
DEFAULT_MEAN_BOOK_GAP = 3.5

MAX_STAT_POINT_EDGE = 10.0

# Minimum std dev as fraction of mean (wider for volatile stats).
STAT_STD_MEAN_RATIO: dict[str, float] = {
    "points": 0.35,
    "rebounds": 0.45,
    "assists": 0.50,
    "three_pointers_made": 0.55,
    "pts+ast+reb": 0.35,
}
STAT_STD_ABSOLUTE_FLOOR: dict[str, float] = {
    "points": 4.0,
    "rebounds": 2.0,
    "assists": 1.5,
    "three_pointers_made": 1.2,
    "pts+ast+reb": 5.0,
}


def mean_book_gap_limit(stat_type: str) -> float:
    return STAT_MEAN_BOOK_GAP.get(stat_type, DEFAULT_MEAN_BOOK_GAP)


def mean_vs_book_misaligned(model_mean: float, book_line: float, stat_type: str) -> bool:
    return abs(model_mean - book_line) > mean_book_gap_limit(stat_type)


def stat_point_edge_exceeds_cap(model_mean: float, book_line: float) -> bool:
    return (model_mean - book_line) > MAX_STAT_POINT_EDGE


def effective_std_for_prop(stat_type: str, mean: float, model_std: Optional[float]) -> float:
    """Inflate narrow model spreads to realistic NBA prop volatility."""
    ratio = STAT_STD_MEAN_RATIO.get(stat_type, 0.40)
    floor_abs = STAT_STD_ABSOLUTE_FLOOR.get(stat_type, 2.0)
    mean_scale = max(abs(mean or 0.0), 0.5)
    min_std = max(floor_abs, ratio * mean_scale)
    if model_std and model_std > 0:
        return max(float(model_std), min_std)
    return min_std


def clamp_probability(p: float) -> float:
    return max(PROB_CLAMP_LOW, min(PROB_CLAMP_HIGH, float(p)))


def shrink_probability(p: float, shrink: float) -> float:
    """Pull probability toward 0.5 (shrink in [0,1])."""
    shrink = max(0.0, min(1.0, float(shrink)))
    return clamp_probability(0.5 + shrink * (float(p) - 0.5))


def raw_probability_over_line(
    mean: float,
    std_dev: float,
    book_line: float,
    stat_type: str = "points",
) -> float:
    if mean is None or book_line is None:
        return PROB_CLAMP_LOW
    sigma = effective_std_for_prop(stat_type, mean, std_dev)
    raw = float(1.0 - norm.cdf(book_line, loc=mean, scale=sigma))
    return clamp_probability(raw)


def probability_over_line(
    mean: float,
    std_dev: float,
    book_line: float,
    stat_type: str = "points",
    *,
    calibrate: bool = True,
    prob_shrink: Optional[float] = None,
) -> float:
    """P(stat > book_line) with std floor, clamp, and optional shrink calibration."""
    raw = raw_probability_over_line(mean, std_dev, book_line, stat_type=stat_type)
    if not calibrate:
        return raw
    if prob_shrink is None:
        from app.services.nba_prop_calibration_store import get_prob_shrink

        prob_shrink = get_prob_shrink()
    if prob_shrink >= 0.999:
        return raw
    return shrink_probability(raw, prob_shrink)


def probability_under_line(
    mean: float,
    std_dev: float,
    book_line: float,
    stat_type: str = "points",
    *,
    calibrate: bool = True,
    prob_shrink: Optional[float] = None,
) -> float:
    p_over = probability_over_line(
        mean,
        std_dev,
        book_line,
        stat_type=stat_type,
        calibrate=calibrate,
        prob_shrink=prob_shrink,
    )
    return clamp_probability(1.0 - p_over)


def probability_edge_exceeds_cap(probability: float, break_even: float) -> bool:
    return (probability - break_even) > MAX_PROB_EDGE


def find_sportsbook_line(
    db: Session,
    game_id: int,
    player_id: int,
    stat_type: str,
) -> Optional[BettingLine]:
    """Best available line for player/stat/game (FanDuel preferred, then DraftKings)."""
    lines = (
        db.query(BettingLine)
        .filter(
            BettingLine.game_id == game_id,
            BettingLine.player_id == player_id,
            BettingLine.stat_type == stat_type,
            BettingLine.over_line.isnot(None),
        )
        .all()
    )
    if not lines:
        return None
    by_book = {ln.sportsbook: ln for ln in lines if ln.sportsbook}
    for preferred in BOOKMAKER_PREFERENCE:
        if preferred in by_book:
            return by_book[preferred]
    return lines[0]
