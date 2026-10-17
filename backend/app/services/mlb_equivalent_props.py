"""
MLB prop equivalences and shared probability helpers.

OVER 0.5 hits and OVER 0.5 total bases are the same betting event (any hit is
at least one total base; walks/HBP do not count toward total bases).
"""
from typing import Any, Dict, Optional, Tuple

# Walk-forward backtest: hits Poisson at 0.5 calibrates better than TB negative binomial.
CANONICAL_STAT_FOR_HIT_OR_TB_OVER_HALF = 'hits'
HIT_OR_TB_OVER_HALF_LINE = 0.5

MLB_PITCHER_PROP_STAT_TYPES = frozenset({
    'strikeouts',
    'innings_pitched',
    'walks_allowed',
    'hits_allowed',
})


def is_hit_or_tb_over_half(stat_type: str, line: Optional[float]) -> bool:
    if line is None:
        return False
    if stat_type not in ('hits', 'total_bases'):
        return False
    return abs(float(line) - HIT_OR_TB_OVER_HALF_LINE) < 1e-9


def suggested_bet_dedup_key(player_id: int, stat_type: str, line: float) -> Tuple:
    """Collapse equivalent OVER 0.5 hit/TB props to one suggested bet per player."""
    if is_hit_or_tb_over_half(stat_type, line):
        return (player_id, 'mlb_hit_or_tb_over_half', HIT_OR_TB_OVER_HALF_LINE)
    return (player_id, stat_type, round(float(line), 1))


def prefer_stat_when_equivalent(stat_type: str) -> int:
    """Lower rank = preferred when deduping equivalent props (hits before total_bases)."""
    if stat_type == 'hits':
        return 0
    if stat_type == 'total_bases':
        return 1
    return 2


def apply_canonical_hit_over_half_probabilities(
    calibrator,
    bet_lines: Dict[str, Any],
    profile: Dict[str, float],
) -> None:
    """
    Rewrite safe/standard/long_shot probabilities at line 0.5 using the shared
    hits-based model (profile must use hits adjusted mean / league mean).
    """
    mean = profile['mean']
    std = profile['std']
    sample_size = int(profile['sample_size'])
    league_mean = profile.get('league_mean')

    for tier in ('safe', 'standard', 'long_shot'):
        line = bet_lines.get(f'{tier}_line')
        prob_key = f'{tier}_probability'
        if line is None or bet_lines.get(prob_key) is None:
            continue
        if not is_hit_or_tb_over_half(CANONICAL_STAT_FOR_HIT_OR_TB_OVER_HALF, line):
            continue
        result = calibrator.calculate_probability_for_line(
            HIT_OR_TB_OVER_HALF_LINE,
            mean,
            std,
            sample_size,
            CANONICAL_STAT_FOR_HIT_OR_TB_OVER_HALF,
            league_mean,
            None,
        )
        bet_lines[prob_key] = result['probability']
