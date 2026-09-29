"""
Calibrated Probability Calculator

Computes calibrated probabilities for betting lines using:
- Student-t distribution for small samples
- Normal distribution for large samples
- Empirical Bayes shrinkage toward league priors
- Base rate adjustment
"""
from typing import Dict, Optional, Tuple
from scipy import stats
import numpy as np


class CalibratedProbabilityCalculator:
    """Calculate calibrated probabilities with shrinkage and base rates."""
    
    # League-wide base rates for different sports and stat types
    BASE_HIT_RATES = {
        'NBA': {
            'points': 0.52,
            'rebounds': 0.51,
            'assists': 0.50,
            'three_pointers_made': 0.48,
            'pts+ast+reb': 0.52,
        },
        'NFL': {
            'passing_yards': 0.50,
            'rushing_yards': 0.49,
            'receiving_yards': 0.48,
            'receptions': 0.51,
            'passing_tds': 0.48,
            'rushing_tds': 0.47,
            'receiving_tds': 0.46,
        },
        'MLB': {
            'hits': 0.48,
            'home_runs': 0.45,
            'total_bases': 0.49,
            'strikeouts': 0.51,
            'runs': 0.47,
            'rbis': 0.48,
        }
    }
    
    def __init__(self, sport: str = 'NBA'):
        """Initialize with sport-specific parameters."""
        self.sport = sport
    
    def calculate_probability_for_line(
        self,
        line: float,
        player_mean: float,
        player_std: float,
        sample_size: int,
        stat_type: str,
        league_mean: Optional[float] = None,
        league_std: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculate calibrated probability of exceeding a line.
        
        Args:
            line: The betting line to evaluate
            player_mean: Player's historical mean
            player_std: Player's historical standard deviation
            sample_size: Number of games in player's history
            stat_type: Type of stat (e.g., 'points', 'passing_yards')
            league_mean: League average for this stat (optional)
            league_std: League standard deviation for this stat (optional)
        
        Returns:
            Dict with 'probability', 'shrunk_mean', 'effective_std', 'effective_n'
        """
        # Apply Empirical Bayes shrinkage to the mean
        if league_mean is not None:
            shrunk_mean, effective_n = self._shrink_mean_toward_prior(
                player_mean, sample_size, league_mean, league_std or player_std
            )
        else:
            shrunk_mean = player_mean
            effective_n = sample_size
        
        # Calculate effective standard deviation (inflated for uncertainty)
        effective_std = self._calculate_effective_std(
            player_std, sample_size, league_std
        )
        
        # Use Student-t for small samples, Normal for large samples
        if sample_size < 30:
            # Student-t distribution with df = sample_size - 1
            df = max(sample_size - 1, 1)
            standardized = (line - shrunk_mean) / effective_std
            raw_prob = 1.0 - stats.t.cdf(standardized, df)
        else:
            # Normal distribution for large samples
            raw_prob = 1.0 - stats.norm.cdf(line, loc=shrunk_mean, scale=effective_std)
        
        # Apply base rate adjustment
        base_hit_rate = self._get_base_hit_rate(stat_type)
        calibrated_prob = self._apply_base_rate_adjustment(
            raw_prob, base_hit_rate, effective_n
        )
        
        # Clamp to valid range
        calibrated_prob = max(0.01, min(0.99, calibrated_prob))
        
        return {
            'probability': round(calibrated_prob, 3),
            'shrunk_mean': round(shrunk_mean, 2),
            'effective_std': round(effective_std, 2),
            'effective_n': effective_n,
            'raw_probability': round(raw_prob, 3)
        }
    
    def _shrink_mean_toward_prior(
        self,
        player_mean: float,
        sample_size: int,
        league_mean: float,
        league_std: float
    ) -> Tuple[float, float]:
        """
        Apply Empirical Bayes shrinkage to player mean toward league prior.
        
        Uses James-Stein style shrinkage: weight player data by sample size.
        
        Returns:
            (shrunk_mean, effective_sample_size)
        """
        # Shrinkage weight: more data = less shrinkage
        # Use a prior strength equivalent to 10 games
        prior_strength = 10.0
        weight_player = sample_size / (sample_size + prior_strength)
        weight_prior = prior_strength / (sample_size + prior_strength)
        
        shrunk_mean = weight_player * player_mean + weight_prior * league_mean
        effective_n = sample_size + prior_strength
        
        return shrunk_mean, effective_n
    
    def _calculate_effective_std(
        self,
        player_std: float,
        sample_size: int,
        league_std: Optional[float]
    ) -> float:
        """
        Calculate effective standard deviation accounting for estimation uncertainty.
        
        For small samples, inflate std to reflect our uncertainty about the true std.
        """
        if sample_size < 30:
            # Inflation factor for small samples
            # At n=5: inflate by ~40%, at n=30: no inflation
            inflation_factor = 1.0 + (30 - sample_size) / 100.0
            effective_std = player_std * inflation_factor
        else:
            effective_std = player_std
        
        # Minimum std to prevent division by zero
        effective_std = max(effective_std, 0.5)
        
        return effective_std
    
    def _get_base_hit_rate(self, stat_type: str) -> float:
        """Get league-wide base hit rate for this stat type."""
        sport_rates = self.BASE_HIT_RATES.get(self.sport, {})
        return sport_rates.get(stat_type, 0.50)  # Default to 50%
    
    def _apply_base_rate_adjustment(
        self,
        raw_prob: float,
        base_hit_rate: float,
        effective_n: float
    ) -> float:
        """
        Adjust probability toward base rate, weighted by sample size.
        
        Small samples get pulled more toward the base rate.
        """
        # Weight base rate inversely with sample size
        # At n=10: weight base rate 50%, at n=50+: weight base rate 5%
        base_weight = min(0.50, 10.0 / effective_n)
        player_weight = 1.0 - base_weight
        
        adjusted_prob = player_weight * raw_prob + base_weight * base_hit_rate
        
        return adjusted_prob
    
    def determine_line_from_distribution(
        self,
        player_mean: float,
        player_std: float,
        sample_size: int,
        stat_type: str,
        real_line: Optional[float] = None,
        league_mean: Optional[float] = None,
        league_std: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Determine the target line and its probability.
        
        If real_line is provided, use it. Otherwise, synthesize from player mean.
        
        Returns:
            Dict with 'line', 'probability', 'line_source', 'is_synthetic'
        """
        if real_line is not None and real_line > 0:
            # Use real betting line
            prob_data = self.calculate_probability_for_line(
                real_line, player_mean, player_std, sample_size, stat_type,
                league_mean, league_std
            )
            return {
                'line': real_line,
                'probability': prob_data['probability'],
                'line_source': 'sportsbook',
                'is_synthetic': False,
                'shrunk_mean': prob_data['shrunk_mean'],
                'effective_std': prob_data['effective_std']
            }
        else:
            # Synthesize line from player mean
            shrunk_mean, _ = self._shrink_mean_toward_prior(
                player_mean, sample_size,
                league_mean or player_mean,
                league_std or player_std
            )
            synthetic_line = round(shrunk_mean, 1)
            
            prob_data = self.calculate_probability_for_line(
                synthetic_line, player_mean, player_std, sample_size, stat_type,
                league_mean, league_std
            )
            
            return {
                'line': synthetic_line,
                'probability': prob_data['probability'],
                'line_source': 'model',
                'is_synthetic': True,
                'shrunk_mean': prob_data['shrunk_mean'],
                'effective_std': prob_data['effective_std']
            }
