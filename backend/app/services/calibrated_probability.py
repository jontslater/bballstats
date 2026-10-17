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

# NFL count-stat shrinkage (receptions, attempts, etc.)
PRIOR_STRENGTH_NFL_RECEPTIONS = float(os.environ.get('K_NFL_REC', '8.0'))
PRIOR_STRENGTH_NFL_ATTEMPTS = float(os.environ.get('K_NFL_ATT', '6.0'))
PRIOR_STRENGTH_NFL_COMPLETIONS = float(os.environ.get('K_NFL_CMP', '6.0'))
PRIOR_STRENGTH_NFL_ANYTIME_TD = float(os.environ.get('K_NFL_ATD', '18.0'))

NFL_COUNT_STATS = {
    'receptions', 'completions', 'attempts', 'pass_attempts',
    'rushing_attempts', 'anytime_td',
}
NFL_COUNT_DISPERSION = {
    'receptions': 1.35,
    'completions': 1.25,
    'attempts': 1.20,
    'pass_attempts': 1.20,
    'rushing_attempts': 1.30,
    'anytime_td': 1.60,
}

NFL_SKEWED_YARDAGE_STATS = frozenset({
    'passing_yards', 'rushing_yards', 'receiving_yards', 'receptions',
})

NFL_QB_COUNT_COMPRESSION_KNEE = 0.62
NFL_QB_COUNT_COMPRESSION_FACTOR = 0.42

# High-end compression to fix overshoot at p >= 0.65
# Compresses probabilities above knee_point by shrinking excess over base rate
# Set via environment for tuning (defaults calibrated from desktop backtest)
COMPRESSION_KNEE = float(os.environ.get('COMPRESSION_KNEE', '0.60'))  # Start compressing above this
COMPRESSION_FACTOR = float(os.environ.get('COMPRESSION_FACTOR', '0.50'))  # Shrink excess by 50%


class CalibratedProbabilityCalculator:
    """Calculate calibrated probabilities with shrinkage and base rates."""

    _nfl_posthoc = None

    @classmethod
    def _get_nfl_posthoc(cls):
        if cls._nfl_posthoc is None:
            from app.services.nfl_posthoc_calibration import NFLPosthocCalibrator
            cls._nfl_posthoc = NFLPosthocCalibrator()
        return cls._nfl_posthoc

    def _finalize_nfl_prob(self, stat_type: str, raw_prob: float) -> Tuple[float, float]:
        """Return (raw_prob, posthoc calibrated_prob) for NFL."""
        if self.sport != 'NFL':
            return raw_prob, raw_prob
        calibrated = self._get_nfl_posthoc().apply(stat_type, raw_prob)
        return raw_prob, calibrated
    
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
            'completions': 0.50,
            'attempts': 0.50,
            'pass_attempts': 0.50,
            'rushing_attempts': 0.49,
            'passing_tds': 0.48,
            'rushing_tds': 0.47,
            'receiving_tds': 0.46,
            'anytime_td': 0.35,
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
    
    def _nfl_skewed_over_probability(
        self,
        line: float,
        player_mean: float,
        player_median: Optional[float],
        player_std: float,
        stat_type: Optional[str] = None,
    ) -> float:
        """Right-skewed yardage/reception model: log-normal anchored at player median."""
        med = float(player_median) if player_median and player_median > 0 else float(player_mean)
        mean = max(float(player_mean), med)
        med = max(med, 0.001)
        ratio = mean / med
        if ratio > 1.02:
            sigma = float(np.sqrt(2.0 * np.log(ratio)))
        elif player_std and mean > 0:
            sigma = float(np.sqrt(np.log(1.0 + (player_std / mean) ** 2)))
        else:
            sigma = 0.35
        if stat_type == "rushing_yards":
            std = float(player_std) if player_std and player_std > 0 else med * 0.28
            std = float(np.clip(std, med * 0.18, med * 0.45))
            loc = max(med * 0.96, 0.5)
            return float(1.0 - stats.norm.cdf(line + 0.5, loc=loc, scale=std))
        sigma = float(np.clip(sigma, 0.12, 0.72))
        return float(1.0 - stats.lognorm.cdf(line + 0.5, s=sigma, scale=med))

    def _nfl_count_over_probability(
        self,
        shrunk_rate: float,
        player_std: float,
        sample_size: int,
        line: float,
        stat_type: str,
        player_median: Optional[float] = None,
    ) -> float:
        """P(X > line) for NFL count props."""
        rate = max(shrunk_rate, 0.001)
        if stat_type in ('receptions', 'rushing_attempts'):
            return self._nfl_skewed_over_probability(
                line, rate, player_median, player_std, stat_type=stat_type
            )
        if sample_size >= 5 and player_std and player_std > 0:
            loc = float(player_median) if player_median and player_median > 0 else rate
            std = float(player_std)
            std = max(std, rate ** 0.5 * 0.75)
            std = min(std, rate * 0.5 + 4.0)
            prob = float(1.0 - stats.norm.cdf(line + 0.5, loc=loc, scale=std))
        else:
            prob = float(1.0 - stats.poisson.cdf(int(line), rate))
        if stat_type in ('attempts', 'pass_attempts', 'completions') and prob > NFL_QB_COUNT_COMPRESSION_KNEE:
            prob = NFL_QB_COUNT_COMPRESSION_KNEE + (
                prob - NFL_QB_COUNT_COMPRESSION_KNEE
            ) * NFL_QB_COUNT_COMPRESSION_FACTOR
        return prob

    def _nfl_apply_qb_count_compression(self, prob: float, stat_type: str) -> float:
        if stat_type in ('attempts', 'pass_attempts', 'completions') and prob > NFL_QB_COUNT_COMPRESSION_KNEE:
            return NFL_QB_COUNT_COMPRESSION_KNEE + (
                prob - NFL_QB_COUNT_COMPRESSION_KNEE
            ) * NFL_QB_COUNT_COMPRESSION_FACTOR
        return prob

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
        league_std: Optional[float] = None,
        player_role: Optional[str] = None,
        player_median: Optional[float] = None,
        apply_posthoc: bool = True,
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
        # NFL count stats: Poisson / Negative Binomial with shrinkage
        if self.sport == 'NFL' and stat_type in NFL_COUNT_STATS:
            if league_mean is not None:
                if stat_type == 'anytime_td':
                    prior_strength = PRIOR_STRENGTH_NFL_ANYTIME_TD
                elif stat_type in ('attempts', 'pass_attempts'):
                    prior_strength = PRIOR_STRENGTH_NFL_ATTEMPTS
                elif stat_type == 'completions':
                    prior_strength = PRIOR_STRENGTH_NFL_COMPLETIONS
                else:
                    prior_strength = PRIOR_STRENGTH_NFL_RECEPTIONS
                if player_role and sample_size >= 6:
                    prior_strength *= 0.45
                weight_player = sample_size / (sample_size + prior_strength)
                shrunk_rate = weight_player * player_mean + (1 - weight_player) * league_mean
            else:
                shrunk_rate = player_mean

            try:
                if stat_type == 'anytime_td':
                    rate = max(shrunk_rate, 0.001)
                    if line <= 0.5:
                        prob = 1.0 - stats.poisson.cdf(0, rate)
                    else:
                        prob = 1.0 - stats.poisson.cdf(int(line), rate)
                else:
                    prob = self._nfl_count_over_probability(
                        shrunk_rate, player_std, sample_size, line, stat_type, player_median
                    )
            except (ValueError, ZeroDivisionError):
                prob = 0.5

            prob = self._nfl_apply_qb_count_compression(prob, stat_type)

            if sample_size < 30 and prob > 0.85:
                prob = 0.85
            prob = max(0.01, min(0.99, prob))
            modeled_prob = prob
            cal_prob = self._get_nfl_posthoc().apply(stat_type, prob) if apply_posthoc else prob
            return {
                'probability': round(cal_prob, 3),
                'calibrated_probability': round(cal_prob, 3),
                'shrunk_mean': round(shrunk_rate, 2),
                'effective_std': round(player_std, 2),
                'effective_n': sample_size,
                'raw_probability': round(modeled_prob, 3),
            }

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
        prior_strength = 10.0
        if self.sport == 'NFL' and player_role:
            prior_strength = 5.0
        if league_mean is not None:
            shrunk_mean, effective_n = self._shrink_mean_toward_prior(
                player_mean, league_mean, sample_size, prior_strength=prior_strength
            )
        else:
            shrunk_mean = player_mean
            effective_n = sample_size
        
        # Calculate effective standard deviation (inflated for uncertainty)
        effective_std = self._calculate_effective_std(
            player_std, sample_size, league_std
        )
        
        if self.sport == 'NFL' and stat_type in NFL_SKEWED_YARDAGE_STATS:
            med = player_median if player_median and player_median > 0 else shrunk_mean
            raw_prob = self._nfl_skewed_over_probability(
                line, player_mean, med, effective_std, stat_type=stat_type
            )
        elif sample_size < 30:
            df = max(sample_size - 1, 1)
            standardized = (line - shrunk_mean) / effective_std
            raw_prob = 1.0 - stats.t.cdf(standardized, df)
        else:
            raw_prob = 1.0 - stats.norm.cdf(line, loc=shrunk_mean, scale=effective_std)

        if self.sport == 'NFL':
            modeled_prob = max(0.01, min(0.99, raw_prob))
            calibrated_prob = (
                self._get_nfl_posthoc().apply(stat_type, modeled_prob) if apply_posthoc else modeled_prob
            )
        else:
            base_hit_rate = self._get_base_hit_rate(stat_type)
            calibrated_prob = self._apply_base_rate_adjustment(
                raw_prob, base_hit_rate, effective_n, stat_type, sport=self.sport
            )
            calibrated_prob = max(0.01, min(0.99, calibrated_prob))

        return {
            'probability': round(calibrated_prob, 3),
            'calibrated_probability': round(calibrated_prob, 3),
            'shrunk_mean': round(shrunk_mean, 2),
            'effective_std': round(effective_std, 2),
            'effective_n': effective_n,
            'raw_probability': round(modeled_prob if self.sport == 'NFL' else raw_prob, 3),
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
        sample_size: int,
        prior_strength: float = 10.0,
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
        stat_type: str = None,
        sport: str = None,
    ) -> float:
        """
        Adjust probability toward base rate, weighted by sample size.
        
        Small samples get pulled more toward the base rate.
        Use stat-specific weighting (home_runs need stronger shrinkage).
        """
        # Base weight inversely proportional to sample size
        # Default: At n=10: 20%, at n=50+: 2%
        if sport == 'NFL':
            return raw_prob
        else:
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
