"""Fit P(over) shrink factor toward 0.5 from labeled samples."""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from app.services.nba_sportsbook_edge import shrink_probability


def fit_prob_shrink_brier(
    samples: Sequence[Tuple[float, bool]],
    *,
    grid_step: float = 0.02,
) -> float:
    """
    Grid-search shrink in [0.3, 1.0] minimizing mean Brier score.
    samples: (raw_p_over, hit_over)
    """
    if not samples:
        return 1.0
    best_shrink = 1.0
    best_loss = float("inf")
    shrink = 0.30
    while shrink <= 1.0001:
        loss = 0.0
        for p_raw, hit in samples:
            p = shrink_probability(p_raw, shrink)
            y = 1.0 if hit else 0.0
            loss += (p - y) ** 2
        loss /= len(samples)
        if loss < best_loss:
            best_loss = loss
            best_shrink = shrink
        shrink += grid_step
    return round(best_shrink, 3)


def collect_prob_samples(
    rows: Iterable[Tuple[float, float, float, str, float]],
) -> List[Tuple[float, bool]]:
    """
    rows: (mean, std, line, stat_type, actual) -> (raw_p, hit)
    """
    from app.services.nba_sportsbook_edge import raw_probability_over_line

    out: List[Tuple[float, bool]] = []
    for mean, std, line, stat_type, actual in rows:
        p = raw_probability_over_line(mean, std, line, stat_type=stat_type)
        out.append((p, actual > line))
    return out
