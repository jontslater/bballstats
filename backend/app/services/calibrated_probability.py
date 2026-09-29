"""
Calibrated Probability Calculator

Computes calibrated probabilities for betting lines using:
- Poisson/Negative Binomial for count stats (hits, home_runs, total_bases)
- Student-t distribution for continuous stats with small samples
- Normal distribution for continuous stats with large samples
- Empirical Bayes shrinkage toward league priors
"""
from typing import Dict, Optional, Tuple, List
from scipy import stats
import numpy as np
import os

# Prior strength constants for MLB count stats (shrinkage toward league rate)
# Higher values = stronger shrinkage to league average (more conservative)
# These can be overridden via environment variables for tuning
PRIOR_STRENGTH_HITS = float(os.environ.get('K_HITS', '18.0'))  # 15-20 range for calibration
PRIOR_STRENGTH_TB = float(os.environ.get('K_TB', '15.0'))  # Re-tuned after NB fix
PRIOR_STRENGTH_HR = float(os.environ.get('K_HR', '40.0'))  # HRs are rare, need stronger shrinkage

# High-end compression to fix overshoot at p >= 0.65
# Compresses probabilities above knee_point by shrinking excess over base rate
# Set via environment for tuning (defaults calibrated from desktop backtest)
COMPRESSION_KNEE = float(os.environ.get('COMPRESSION_KNEE', '0.60'))  # Start compressing above this
COMPRESSION_FACTOR = float(os.environ.get('COMPRESSION_FACTOR', '0.50'))  # Shrink excess by 50%


class CalibratedProbabilityCalculator:
    """Calculate calibrated probabilities with shrinkage and base rates."""
    
    # League-wide base rates for different sports and stat types
    # These are P(player exceeds typical line) not per-game averages
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
            # P(hits >= 1) for a starter: ~60-65%
            # P(total_bases >= 1): ~60-65%
            # P(home_runs >= 1): ~10-15% (very rare)
            'hits': 0.62,  # Reduced from 0.67
            'home_runs': 0.12,  # Reduced from 0.18 - HRs are very rare
            'total_bases': 0.62,  # Reduced from 0.68
            'rbis': 0.48,
            'strikeouts': 0.52,  # For pitchers
        }
    }
    
    def __init__(self, sport: str = 'NBA'):
        """Initialize with sport-specific parameters."""
        self.sport = sport
    
    def _apply_high_end_compression(
        self,
        prob: float,
        stat_type: str,
        line: float
    ) -> float:
        """
        Apply high-end compression to fix overshoot at p >= 0.65.
        
        Desktop backtest showed TB/hits at p>=0.65 overshoot by ~7-10 pts.
        Compress probabilities above knee_point using strictly monotone transformation.
        
        Formula: p' = knee + (p - knee) * factor for p > knee
        
        Maintains strict monotonicity: higher raw prob -> higher compressed prob (no clamping).
        """
        if self.sport != 'MLB' or prob <= COMPRESSION_KNEE:
            return prob
        
        # Strictly monotone compression above knee: apply factor to excess only
        # p' = knee + (p - knee) * factor
        # This ensures p1 > p2 => p1' > p2' (no ties from clamping)
        prob = COMPRESSION_KNEE + (prob - COMPRESSION_KNEE) * COMPRESSION_FACTOR
        
        return prob
    
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
        
        For MLB count stats, uses discrete Poisson/Negative Binomial.
        For other stats, uses Normal/Student-t with shrinkage and base rate adjustment.
        
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
        # For MLB count stats, use discrete Poisson/Negative Binomial model
        if self.sport == 'MLB' and stat_type in ['hits', 'home_runs', 'total_bases']:
            # Shrinkage toward league rate using module-level constants
            if league_mean is not None:
                if stat_type == 'home_runs':
                    prior_strength = PRIOR_STRENGTH_HR
                elif stat_type == 'total_bases':
                    prior_strength = PRIOR_STRENGTH_TB
                else:  # hits
                    prior_strength = PRIOR_STRENGTH_HITS
                
                weight_player = sample_size / (sample_size + prior_strength)
                shrunk_rate = weight_player * player_mean + (1 - weight_player) * league_mean
            else:
                shrunk_rate = player_mean
            
            # Use league-pooled dispersion for over-dispersed stats
            # Computed from league data: TB ~2.25, hits ~1.1, HR ~1.5
            league_dispersion = {
                'total_bases': 2.25,
                'hits': 1.1,
                'home_runs': 1.5
            }
            dispersion = league_dispersion.get(stat_type, 1.0)
            
            # Choose distribution
            try:
                if dispersion > 1.5:
                    # Negative Binomial for over-dispersed data (TB, HR)
                    # Use shrunk_rate (not raw player_mean) with league-pooled dispersion
                    if shrunk_rate > 0:
                        # NB parameterization: variance = mean + mean^2/r
                        # From dispersion = var/mean: var = dispersion * mean
                        variance = dispersion * shrunk_rate
                        if variance > shrunk_rate:
                            r = (shrunk_rate ** 2) / (variance - shrunk_rate)
                            p_nb = shrunk_rate / variance
                            prob = 1.0 - stats.nbinom.cdf(int(line), r, p_nb)
                        else:
                            # Fallback to Poisson if variance calculation fails
                            prob = 1.0 - stats.poisson.cdf(int(line), shrunk_rate)
                    else:
                        prob = 0.5
                else:
                    # Poisson for standard count data (hits)
                    prob = 1.0 - stats.poisson.cdf(int(line), shrunk_rate)
            except (ValueError, ZeroDivisionError):
                # Fallback to 50%
                prob = 0.5
            
            # Cap probability for small samples (avoid overconfidence)
            # Never above 0.85 unless n >= 30
            if sample_size < 30 and prob > 0.85:
                prob = 0.85
            
            # Apply high-end compression to fix overshoot at p >= 0.65
            prob = self._apply_high_end_compression(prob, stat_type, line)
            
            # Clamp
            prob = max(0.01, min(0.99, prob))
            
            return {
                'probability': round(prob, 3),
                'shrunk_mean': round(shrunk_rate, 2),
                'effective_std': round(player_std, 2),
                'effective_n': sample_size,
                'raw_probability': round(prob, 3)
            }
        
        # For continuous stats or non-MLB, use Normal/Student-t
        # Apply Empirical Bayes shrinkage to the mean
        if league_mean is not None:
            shrunk_mean, effective_n = self._shrink_mean_toward_prior(
                player_mean, league_mean, sample_size
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
            raw_prob, base_hit_rate, effective_n, stat_type
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
    
    def calculate_discrete_probability(
        self,
        stat_values: List[int],
        line: float,
        stat_type: str,
        league_mean: Optional[float] = None
    ) -> Dict[str, any]:
        """
        Calculate P(X > line) using discrete Poisson/Negative Binomial model.
        
        For count stats (hits, home_runs, total_bases), use proper discrete distribution
        instead of Normal/Student-t approximation.
        
        Args:
            stat_values: List of historical stat values (integers)
            line: Betting line (e.g., 0.5 for OVER 0.5)
            stat_type: Type of stat
            league_mean: League average per-game rate
        
        Returns:
            Dict with 'probability', 'shrunk_rate', 'dispersion'
        """
        if not stat_values:
            return {'probability': 0.5, 'shrunk_rate': 0.5, 'dispersion': 1.0}
        
        sample_size = len(stat_values)
        player_mean = sum(stat_values) / sample_size
        
        # Shrinkage toward league rate (stronger for rare events) using module-level constants
        if league_mean is not None:
            if stat_type == 'home_runs':
                prior_strength = PRIOR_STRENGTH_HR
            elif stat_type == 'total_bases':
                prior_strength = PRIOR_STRENGTH_TB
            else:  # hits
                prior_strength = PRIOR_STRENGTH_HITS
            
            weight_player = sample_size / (sample_size + prior_strength)
            shrunk_rate = weight_player * player_mean + (1 - weight_player) * league_mean
        else:
            shrunk_rate = player_mean
        
        # Use league-pooled dispersion for over-dispersed stats
        # Computed from league data: TB ~2.25, hits ~1.1, HR ~1.5
        league_dispersion = {
            'total_bases': 2.25,
            'hits': 1.1,
            'home_runs': 1.5
        }
        dispersion = league_dispersion.get(stat_type, 1.0)
        
        # Choose distribution based on dispersion
        try:
            if dispersion > 1.5:
                # Negative Binomial for over-dispersed data (TB, HR)
                # Use shrunk_rate with league-pooled dispersion
                if shrunk_rate > 0:
                    variance = dispersion * shrunk_rate
                    if variance > shrunk_rate:
                        r = (shrunk_rate ** 2) / (variance - shrunk_rate)
                        p_nb = shrunk_rate / variance
                        prob = 1.0 - stats.nbinom.cdf(int(line), r, p_nb)
                    else:
                        prob = 1.0 - stats.poisson.cdf(int(line), shrunk_rate)
                else:
                    prob = 0.5
            else:
                # Use Poisson (simpler, works well for count data)
                prob = 1.0 - stats.poisson.cdf(int(line), shrunk_rate)
        except (ValueError, ZeroDivisionError):
            # Fallback to simple calculation
            prob = 0.5
        
        # Apply high-end compression to fix overshoot at p >= 0.65
        prob = self._apply_high_end_compression(prob, stat_type, line)
        
        # Clamp to valid range
        prob = max(0.01, min(0.99, prob))
        
        return {
            'probability': round(prob, 3),
            'shrunk_rate': round(shrunk_rate, 3),
            'dispersion': round(dispersion, 2)
        }
    
    def _shrink_mean_toward_prior(
        self,
        player_mean: float,
        league_mean: float,
        sample_size: int
    ) -> Tuple[float, float]:
        """
        Apply Empirical Bayes shrinkage to player mean toward league prior.
        
        Uses James-Stein style shrinkage: weight player data by sample size.
        Prior strength = 10 games for shrinkage calculation.
        
        Returns:
            (shrunk_mean, actual_sample_size)
            
        Note: We shrink using prior_strength but return the REAL sample_size
        (not inflated by pseudo-observations) for display to users.
        """
        # Shrinkage weight: more data = less shrinkage
        # Use a prior strength equivalent to 10 games
        prior_strength = 10.0
        weight_player = sample_size / (sample_size + prior_strength)
        weight_prior = prior_strength / (sample_size + prior_strength)
        
        shrunk_mean = weight_player * player_mean + weight_prior * league_mean
        
        # Return REAL sample size, not inflated by prior pseudo-observations
        # effective_n for statistical purposes uses prior_strength internally,
        # but we report the actual games played to the user
        return shrunk_mean, sample_size
    
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
        effective_n: float,
        stat_type: str = None
    ) -> float:
        """
        Adjust probability toward base rate, weighted by sample size.
        
        Small samples get pulled more toward the base rate.
        Use stat-specific weighting (home_runs need stronger shrinkage).
        """
        # Base weight inversely proportional to sample size
        # Default: At n=10: 20%, at n=50+: 2%
        base_weight = min(0.20, 5.0 / effective_n)
        
        # Home runs need stronger shrinkage toward base rate (they're rare)
        if stat_type == 'home_runs':
            base_weight = min(0.40, 15.0 / effective_n)  # Double the weight
        
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
                player_mean,
                league_mean or player_mean,
                sample_size
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
