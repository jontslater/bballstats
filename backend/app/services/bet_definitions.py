"""
Bet Definitions

Defines safe, standard, and long shot bet lines and probabilities.
"""
from scipy.stats import norm
from typing import Dict, Optional


class BetDefinitions:
    """Define bet types and calculate lines/probabilities."""
    
    def __init__(self, calibration_data: Optional[Dict] = None):
        """
        Initialize with optional probability calibration data.
        
        Args:
            calibration_data: Dict mapping probability ranges to calibration adjustments
        """
        self.calibration_data = calibration_data or {}
    
    def calculate_bet_lines(
        self,
        adjusted_mean: float,
        adjusted_std: float,
        percentiles: Dict[int, float],
        apply_calibration: bool = True
    ) -> Dict[str, float]:
        """
        Calculate bet lines and probabilities from distribution.
        
        Args:
            adjusted_mean: Adjusted mean (μ)
            adjusted_std: Adjusted standard deviation (σ)
            percentiles: Dict of percentile values
        
        Returns:
            Dict with bet lines and probabilities
        """
        # Create distribution
        dist = norm(loc=adjusted_mean, scale=adjusted_std)
        
        # Safe bet: 25th percentile (~75% probability)
        safe_line = percentiles.get(25, adjusted_mean * 0.85)
        safe_probability = float(1.0 - dist.cdf(safe_line))  # Probability of exceeding line
        
        # Standard bet: 50th percentile/median (~50% probability)
        standard_line = percentiles.get(50, adjusted_mean)
        standard_probability = float(1.0 - dist.cdf(standard_line))
        
        # Long shot: 85th percentile (~15% probability)
        long_shot_line = percentiles.get(85, adjusted_mean * 1.15)
        long_shot_probability = float(1.0 - dist.cdf(long_shot_line))
        
        # Apply probability calibration if available
        if apply_calibration and self.calibration_data:
            safe_probability = self._apply_calibration(safe_probability)
            standard_probability = self._apply_calibration(standard_probability)
            long_shot_probability = self._apply_calibration(long_shot_probability)
        
        return {
            'safe_line': round(float(safe_line), 2),
            'safe_probability': round(float(safe_probability), 3),
            'standard_line': round(float(standard_line), 2),
            'standard_probability': round(float(standard_probability), 3),
            'long_shot_line': round(float(long_shot_line), 2),
            'long_shot_probability': round(float(long_shot_probability), 3)
        }
    
    def _apply_calibration(self, raw_probability: float) -> float:
        """
        Apply calibration adjustment to a raw probability.
        
        Args:
            raw_probability: Raw probability from distribution (0.0 to 1.0)
        
        Returns:
            Calibrated probability
        """
        if not self.calibration_data:
            return raw_probability
        
        # Find the calibration range that contains this probability
        for range_name, cal_data in self.calibration_data.items():
            if 'expected' in cal_data and 'adjustment' in cal_data:
                # Parse range (e.g., "0.70-0.75")
                try:
                    range_parts = range_name.split('-')
                    if len(range_parts) == 2:
                        min_prob = float(range_parts[0])
                        max_prob = float(range_parts[1])
                        
                        if min_prob <= raw_probability < max_prob:
                            # Apply calibration adjustment
                            adjustment = cal_data.get('adjustment', 1.0)
                            calibrated = raw_probability * adjustment
                            # Clamp to valid range
                            return max(0.0, min(1.0, calibrated))
                except (ValueError, IndexError):
                    continue
        
        # If no matching range found, return original
        return raw_probability
    
    @staticmethod
    def determine_bet_type(
        safe_probability: float,
        standard_probability: float,
        long_shot_probability: float,
        should_pass: bool
    ) -> str:
        """
        Determine recommended bet type.
        
        Returns:
            'safe', 'standard', 'long_shot', or 'pass'
        """
        if should_pass:
            return 'pass'
        
        # Priority order: safe > standard > long_shot
        # But allow long shots even if safe bets exist (for variety)
        
        # Safe bets: high probability (≥70%)
        if safe_probability >= 0.70:
            return 'safe'
        
        # Standard bets: moderate probability (≥45%)
        if standard_probability >= 0.45:
            return 'standard'
        
        # Long shots: lower probability but still reasonable (8-30%)
        # Expanded range to generate more long shots
        if 0.08 <= long_shot_probability <= 0.30:
            return 'long_shot'
        
        # If safe probability is decent but not great, could be standard
        if safe_probability >= 0.60:
            return 'standard'
        
        # Default to pass if nothing looks good
        return 'pass'

