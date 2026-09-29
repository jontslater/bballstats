"""
Bet Definitions

Defines safe, standard, and long shot bet lines and probabilities using calibrated methods.
"""
from typing import Dict, Optional
from app.services.calibrated_probability import CalibratedProbabilityCalculator


class BetDefinitions:
    """Define bet types and calculate lines/probabilities using calibrated methods."""
    
    def __init__(self, sport: str = 'NBA'):
        """
        Initialize with sport-specific configuration.
        
        Args:
            sport: Sport type ('NBA', 'NFL', or 'MLB')
        """
        self.sport = sport
        self.calibrator = CalibratedProbabilityCalculator(sport)
    
    def calculate_bet_lines(
        self,
        adjusted_mean: float,
        adjusted_std: float,
        sample_size: int,
        stat_type: str,
        real_line: Optional[float] = None,
        league_mean: Optional[float] = None,
        league_std: Optional[float] = None
    ) -> Dict[str, any]:
        """
        Calculate bet lines and calibrated probabilities.
        
        Strategy:
        1. Determine target line (real if available, else synthetic from mean)
        2. Calculate calibrated probability using Student-t or Normal distribution
        3. Apply Empirical Bayes shrinkage and base rate adjustment
        4. Generate safe/standard/long-shot variants around the target
        
        Args:
            adjusted_mean: Adjusted mean (μ) after all adjustments
            adjusted_std: Adjusted standard deviation (σ)
            sample_size: Number of games in history
            stat_type: Type of stat (e.g., 'points', 'passing_yards')
            real_line: Real sportsbook line (if available)
            league_mean: League average for this stat
            league_std: League standard deviation
        
        Returns:
            Dict with lines, probabilities, and metadata
        """
        # Determine primary line and its probability
        primary = self.calibrator.determine_line_from_distribution(
            adjusted_mean, adjusted_std, sample_size, stat_type,
            real_line, league_mean, league_std
        )
        
        target_line = primary['line']
        line_source = primary['line_source']
        is_synthetic = primary['is_synthetic']
        
        # Calculate probabilities for standard bet tiers around the target
        # Safe: lower line (higher probability)
        # Standard: target line (moderate probability)
        # Long shot: higher line (lower probability)
        
        # Safe line: 15% below target (or use percentile-based if preferred)
        safe_line = target_line * 0.85
        safe_data = self.calibrator.calculate_probability_for_line(
            safe_line, adjusted_mean, adjusted_std, sample_size, stat_type,
            league_mean, league_std
        )
        
        # Standard line: use target
        standard_line = target_line
        standard_data = self.calibrator.calculate_probability_for_line(
            standard_line, adjusted_mean, adjusted_std, sample_size, stat_type,
            league_mean, league_std
        )
        
        # Long shot: 15% above target
        long_shot_line = target_line * 1.15
        long_shot_data = self.calibrator.calculate_probability_for_line(
            long_shot_line, adjusted_mean, adjusted_std, sample_size, stat_type,
            league_mean, league_std
        )
        
        return {
            'safe_line': round(safe_line, 2),
            'safe_probability': safe_data['probability'],
            'standard_line': round(standard_line, 2),
            'standard_probability': standard_data['probability'],
            'long_shot_line': round(long_shot_line, 2),
            'long_shot_probability': long_shot_data['probability'],
            'line_source': line_source,
            'is_synthetic': is_synthetic,
            'shrunk_mean': standard_data['shrunk_mean'],
            'effective_std': standard_data['effective_std'],
            'effective_n': standard_data['effective_n']
        }
    
    @staticmethod
    def determine_bet_type(
        safe_probability: float,
        standard_probability: float,
        long_shot_probability: float
    ) -> str:
        """
        Determine recommended bet type based on calibrated probabilities.
        
        Uses realistic thresholds (no flat 0.75/0.60/0.25 fallbacks).
        
        Returns:
            'safe', 'standard', 'long_shot', or 'pass'
        """
        # Safe bets: genuinely high probability (≥65%)
        if safe_probability >= 0.65:
            return 'safe'
        
        # Standard bets: moderate probability (≥45%)
        if standard_probability >= 0.45:
            return 'standard'
        
        # Long shots: lower probability but reasonable (10-35%)
        if 0.10 <= long_shot_probability <= 0.35:
            return 'long_shot'
        
        # Default to pass if nothing qualifies
        return 'pass'
