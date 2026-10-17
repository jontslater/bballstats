"""
Holdout metrics and bettable-prop gates for NFL post-hoc calibration.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

MEDIAN_P_OVER_LOW = 0.45
MEDIAN_P_OVER_HIGH = 0.55
BUCKET_GAP_MAX = 0.08
BRIER_IMPROVE_EPS = 0.0001

# Primary calibration buckets (50–69% and 70+)
REPORT_BUCKETS = (
    "0.50-0.54",
    "0.55-0.59",
    "0.60-0.64",
    "0.65-0.69",
    "0.70-0.74",
    "0.75-0.79",
    "0.80-0.84",
    "0.85-0.89",
    "0.90-1.00",
)

BETTABLE_BUCKET_CHECKS = ("0.50-0.54", "0.55-0.59")


def bucket_probability(prob: float) -> str:
    if prob < 0.50:
        return "0.00-0.49"
    elif prob < 0.55:
        return "0.50-0.54"
    elif prob < 0.60:
        return "0.55-0.59"
    elif prob < 0.65:
        return "0.60-0.64"
    elif prob < 0.70:
        return "0.65-0.69"
    elif prob < 0.75:
        return "0.70-0.74"
    elif prob < 0.80:
        return "0.75-0.79"
    elif prob < 0.85:
        return "0.80-0.84"
    elif prob < 0.90:
        return "0.85-0.89"
    return "0.90-1.00"


def brier(pairs: List[Tuple[float, int]]) -> float:
    if not pairs:
        return 0.0
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def aggregate_bucket_stats(
    pairs: List[Tuple[float, int]],
) -> Dict[str, Dict[str, float]]:
    buckets: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"n": 0, "hits": 0.0, "sum_p": 0.0}
    )
    for p, y in pairs:
        b = bucket_probability(p)
        buckets[b]["n"] += 1
        buckets[b]["hits"] += y
        buckets[b]["sum_p"] += p
    out: Dict[str, Dict[str, float]] = {}
    for name, b in buckets.items():
        n = int(b["n"])
        if n == 0:
            continue
        out[name] = {
            "n": n,
            "mean_predicted": b["sum_p"] / n,
            "actual_hit_rate": b["hits"] / n,
            "gap": (b["hits"] / n) - (b["sum_p"] / n),
        }
    return out


def median_line_avg(median_probs: List[float]) -> float:
    return sum(median_probs) / len(median_probs) if median_probs else 0.0


def prop_passes_bettable_criteria(
    *,
    median_avg_p_over: float,
    buckets: Dict[str, Dict[str, float]],
    brier_raw: float,
    brier_posthoc: float,
    min_bucket_n: int = 25,
) -> Tuple[bool, List[str]]:
    """All gates must pass for a prop to be suggested-bet eligible."""
    reasons: List[str] = []
    if not (MEDIAN_P_OVER_LOW <= median_avg_p_over <= MEDIAN_P_OVER_HIGH):
        reasons.append(
            f"median P(over)={median_avg_p_over:.3f} outside "
            f"[{MEDIAN_P_OVER_LOW}, {MEDIAN_P_OVER_HIGH}]"
        )
    if brier_posthoc > brier_raw + BRIER_IMPROVE_EPS:
        reasons.append(
            f"posthoc Brier {brier_posthoc:.4f} worse than raw {brier_raw:.4f}"
        )
    for bucket in BETTABLE_BUCKET_CHECKS:
        b = buckets.get(bucket)
        if not b or b["n"] < min_bucket_n:
            continue
        gap = abs(b["gap"])
        if gap > BUCKET_GAP_MAX:
            reasons.append(
                f"bucket {bucket} gap {gap:.3f} > {BUCKET_GAP_MAX} "
                f"(n={int(b['n'])})"
            )
    return (len(reasons) == 0, reasons)


def format_bucket_table(buckets: Dict[str, Dict[str, float]]) -> str:
    lines = []
    for bucket in REPORT_BUCKETS:
        b = buckets.get(bucket)
        if not b:
            continue
        lines.append(
            f"  {bucket}: n={int(b['n']):4d} "
            f"pred={b['mean_predicted']:.3f} actual={b['actual_hit_rate']:.3f} "
            f"gap={b['gap']:+.3f}"
        )
    return "\n".join(lines)
