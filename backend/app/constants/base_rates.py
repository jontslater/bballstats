"""
MLB Base Rates Constants

League-wide empirical base rates for P(stat > line) computed from all-history data.
These are the probabilities that a random MLB player exceeds the given line.

Consolidated from desktop backtest verification (commit a227d2a).
"""

# Stat/line-specific base rates: P(stat > line) from league data
# Format: (stat_type, line) -> probability
MLB_STAT_LINE_BASE_RATES = {
    # Hits: all-history rate is ~56.3% for OVER 0.5
    ('hits', 0.5): 0.563,
    ('hits', 1.5): 0.26,
    ('hits', 2.5): 0.10,
    
    # Total bases: all-history rate is ~56.3% for OVER 0.5
    ('total_bases', 0.5): 0.563,
    ('total_bases', 1.5): 0.38,
    ('total_bases', 2.5): 0.20,
    ('total_bases', 3.5): 0.10,
    
    # Home runs: all-history rate is ~10.7% for OVER 0.5
    ('home_runs', 0.5): 0.107,
    ('home_runs', 1.5): 0.01,
    
    # Other stats (if needed)
    ('strikeouts', 0.5): 0.50,  # Pitchers, more variable
}


def get_base_rate(stat_type: str, line: float, default: float = 0.50) -> float:
    """
    Get the league base rate for a stat/line combination.
    
    Args:
        stat_type: Type of stat ('hits', 'total_bases', 'home_runs', etc.)
        line: Betting line (e.g., 0.5, 1.5)
        default: Default probability if not found (default: 0.50)
    
    Returns:
        Base rate probability or default if not in table
    """
    line_rounded = round(line, 1)
    return MLB_STAT_LINE_BASE_RATES.get((stat_type, line_rounded), default)
