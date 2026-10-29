"""
NBA sportsbook line matching and edge math for suggested bets.
"""
from __future__ import annotations

from typing import Optional

from scipy.stats import norm
from sqlalchemy.orm import Session

from app.models.betting_line import BettingLine

BOOKMAKER_PREFERENCE = ("FanDuel", "DraftKings")

# Max |model mean − book line| before treating as misaligned data.
STAT_MEAN_BOOK_GAP: dict[str, float] = {
    "points": 4.0,
    "rebounds": 2.5,
    "assists": 2.5,
    "three_pointers_made": 1.5,
    "pts+ast+reb": 4.0,
}
DEFAULT_MEAN_BOOK_GAP = 3.5

# Skip when model mean exceeds book line by this many stat units (over-only edge sanity).
MAX_STAT_POINT_EDGE = 10.0


def mean_book_gap_limit(stat_type: str) -> float:
    return STAT_MEAN_BOOK_GAP.get(stat_type, DEFAULT_MEAN_BOOK_GAP)


def mean_vs_book_misaligned(model_mean: float, book_line: float, stat_type: str) -> bool:
    return abs(model_mean - book_line) > mean_book_gap_limit(stat_type)


def stat_point_edge_exceeds_cap(model_mean: float, book_line: float) -> bool:
    return (model_mean - book_line) > MAX_STAT_POINT_EDGE


def probability_over_line(mean: float, std_dev: float, book_line: float) -> float:
    """P(stat > book_line) using normal approximation on the stored distribution."""
    if mean is None or book_line is None:
        return 0.0
    sigma = std_dev if std_dev and std_dev > 0 else max(abs(mean) * 0.15, 1.0)
    return float(1.0 - norm.cdf(book_line, loc=mean, scale=sigma))


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
            BettingLine.over_odds.isnot(None),
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
