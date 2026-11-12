"""Fit P(over) calibration: widen sigma and optional mild shrink toward 0.5."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

from app.services.nba_sportsbook_edge import shrink_probability


def _bucket_key(p: float) -> str:
    return f"{int(p * 10) * 10}-{int(p * 10) * 10 + 10}%"


def _predicted_p(
    mean: float,
    std: float,
    line: float,
    stat_type: str,
    *,
    sigma_scale: float,
    shrink: float,
) -> float:
    from app.services.nba_sportsbook_edge import raw_probability_over_line

    raw = raw_probability_over_line(
        mean,
        std,
        line,
        stat_type=stat_type,
        sigma_scale=sigma_scale,
    )
    if shrink >= 0.999:
        return raw
    return shrink_probability(raw, shrink)


def _bucket_calibration_loss(
    rows: Sequence[Tuple[float, float, float, str, bool]],
) -> float:
    buckets: Dict[str, List[Tuple[float, bool]]] = defaultdict(list)
    for p, hit in rows:
        buckets[_bucket_key(p)].append((p, hit))
    loss = 0.0
    n_total = 0
    for _b, items in buckets.items():
        n = len(items)
        if n < 3:
            continue
        pred_avg = sum(p for p, _h in items) / n
        hit_rate = sum(1 for _p, h in items if h) / n
        loss += n * (pred_avg - hit_rate) ** 2
        n_total += n
    return loss / n_total if n_total else float("inf")


def collect_prob_rows(
    samples: Iterable[Tuple[float, float, float, str, float]],
) -> List[Tuple[float, float, float, str, float]]:
    return list(samples)


def fit_prob_calibration(
    rows: Sequence[Tuple[float, float, float, str, float]],
    *,
    sigma_step: float = 0.05,
    shrink_step: float = 0.05,
) -> Tuple[float, float]:
    """
    Grid-search (sigma_scale, shrink) on median-line rows.
    Prefers sigma widening over crushing probabilities toward 50%.
    """
    if not rows:
        return 1.0, 1.0
    best_sigma = 1.0
    best_shrink = 1.0
    best_loss = float("inf")
    sigma = 1.0
    while sigma <= 1.6501:
        shrink = 0.75
        while shrink <= 1.0001:
            scored: List[Tuple[float, bool]] = []
            for mean, std, line, stat_type, actual in rows:
                p = _predicted_p(
                    mean,
                    std,
                    line,
                    stat_type,
                    sigma_scale=sigma,
                    shrink=shrink,
                )
                scored.append((p, actual > line))
            loss = _bucket_calibration_loss(scored)
            brier = sum((p - (1.0 if h else 0.0)) ** 2 for p, h in scored) / len(scored)
            combined = loss + 0.15 * brier
            if combined < best_loss:
                best_loss = combined
                best_sigma = sigma
                best_shrink = shrink
            shrink += shrink_step
        sigma += sigma_step
    if best_shrink < 0.80:
        best_shrink = 0.80
    return round(best_sigma, 3), round(best_shrink, 3)


# Backward-compatible helper
def fit_prob_shrink_brier(
    samples: Sequence[Tuple[float, bool]],
    *,
    grid_step: float = 0.02,
) -> float:
    _ = samples
    _ = grid_step
    return 1.0


def collect_prob_samples(
    rows: Iterable[Tuple[float, float, float, str, float]],
) -> List[Tuple[float, bool]]:
    from app.services.nba_sportsbook_edge import raw_probability_over_line

    out: List[Tuple[float, bool]] = []
    for mean, std, line, stat_type, actual in rows:
        p = raw_probability_over_line(mean, std, line, stat_type=stat_type)
        out.append((p, actual > line))
    return out
