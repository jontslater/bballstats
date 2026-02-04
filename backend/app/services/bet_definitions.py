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
            safe_probability = self._apply_calibration(safe_probability, 'safe')
            standard_probability = self._apply_calibration(standard_probability, 'standard')
            long_shot_probability = self._apply_calibration(long_shot_probability, 'long_shot')
        
        # ENHANCEMENT: Optimize lines for over/under balance
        # Adjust lines slightly to get closer to 50/50 over/under split for better betting value
        optimized_lines = self._optimize_lines_for_over_under_balance(
            dist, safe_line, standard_line, long_shot_line
        )
        safe_line = optimized_lines['safe_line']
        standard_line = optimized_lines['standard_line']
        long_shot_line = optimized_lines['long_shot_line']

        # Recalculate probabilities with optimized lines
        safe_probability = float(1.0 - dist.cdf(safe_line))
        standard_probability = float(1.0 - dist.cdf(standard_line))
        long_shot_probability = float(1.0 - dist.cdf(long_shot_line))

        return {
            'safe_line': round(float(safe_line), 2),
            'safe_probability': round(float(safe_probability), 3),
            'standard_line': round(float(standard_line), 2),
            'standard_probability': round(float(standard_probability), 3),
            'long_shot_line': round(float(long_shot_line), 2),
            'long_shot_probability': round(float(long_shot_probability), 3)
        }

    def _optimize_lines_for_over_under_balance(
        self,
        dist,
        safe_line: float,
        standard_line: float,
        long_shot_line: float
    ) -> Dict[str, float]:
        """
        Optimize betting lines to balance over/under probabilities closer to 50/50.

        This provides better betting value by finding lines where the market is most efficient.

        Args:
            dist: Normal distribution object
            safe_line: Original safe bet line
            standard_line: Original standard bet line
            long_shot_line: Original long shot line

        Returns:
            Dict with optimized lines
        """
        optimized_lines = {
            'safe_line': safe_line,
            'standard_line': standard_line,
            'long_shot_line': long_shot_line
        }

        # Only optimize if we have a reasonable distribution
        if dist.std() < 1.0:  # Too tight, don't optimize
            return optimized_lines

        # For each line type, find the line that gets closest to 50/50 over/under
        target_prob = 0.50  # Target 50/50 over/under split
        search_range = dist.std() * 0.3  # Search within ±30% of std dev
        search_steps = 10

        # Optimize safe line
        best_safe_line = safe_line
        best_safe_balance = abs(dist.sf(safe_line) - target_prob)  # sf = survival function (1 - cdf)

        for i in range(-search_steps, search_steps + 1):
            test_line = safe_line + (i * search_range / search_steps)
            over_prob = dist.sf(test_line)  # Probability of exceeding line
            under_prob = 1.0 - over_prob
            balance_score = abs(over_prob - under_prob)  # How close to 50/50

            if balance_score < best_safe_balance:
                best_safe_balance = balance_score
                best_safe_line = test_line

        # Optimize standard line
        best_standard_line = standard_line
        best_standard_balance = abs(dist.sf(standard_line) - target_prob)

        for i in range(-search_steps, search_steps + 1):
            test_line = standard_line + (i * search_range / search_steps)
            over_prob = dist.sf(test_line)
            under_prob = 1.0 - over_prob
            balance_score = abs(over_prob - under_prob)

            if balance_score < best_standard_balance:
                best_standard_balance = balance_score
                best_standard_line = test_line

        # Optimize long shot line
        best_long_shot_line = long_shot_line
        best_long_shot_balance = abs(dist.sf(long_shot_line) - target_prob)

        for i in range(-search_steps, search_steps + 1):
            test_line = long_shot_line + (i * search_range / search_steps)
            over_prob = dist.sf(test_line)
            under_prob = 1.0 - over_prob
            balance_score = abs(over_prob - under_prob)

            if balance_score < best_long_shot_balance:
                best_long_shot_balance = balance_score
                best_long_shot_line = test_line

        # Only apply optimization if it significantly improves balance
        # Require at least 5% improvement in balance
        safe_improvement = abs(dist.sf(safe_line) - target_prob) - best_safe_balance
        standard_improvement = abs(dist.sf(standard_line) - target_prob) - best_standard_balance
        long_shot_improvement = abs(dist.sf(long_shot_line) - target_prob) - best_long_shot_balance

        if safe_improvement > 0.05:
            optimized_lines['safe_line'] = best_safe_line
        if standard_improvement > 0.05:
            optimized_lines['standard_line'] = best_standard_line
        if long_shot_improvement > 0.05:
            optimized_lines['long_shot_line'] = best_long_shot_line

        return optimized_lines

    def _apply_calibration(self, raw_probability: float, bet_type: str) -> float:
        """
        Apply calibration adjustment to a raw probability.
        
        Args:
            raw_probability: Raw probability from distribution (0.0 to 1.0)
            bet_type: Type of bet ('safe', 'standard', or 'long_shot')
        
        Returns:
            Calibrated probability
        """
        if not self.calibration_data:
            return raw_probability
        
        # Use calibration data for the specific bet type
        if bet_type not in self.calibration_data:
            return raw_probability
        
        # Find the calibration range that contains this probability
        for range_label, cal_data in self.calibration_data[bet_type].items():
            min_prob = cal_data.get('min_prob', 0.0)
            max_prob = cal_data.get('max_prob', 1.0)
            adjustment = cal_data.get('adjustment', 0.0)
            
            if min_prob <= raw_probability < max_prob:
                # Apply calibration adjustment (additive adjustment)
                # If we predicted 75% but only hit 65%, adjustment = -0.10
                # So calibrated = 0.75 + (-0.10) = 0.65
                calibrated = raw_probability + adjustment
                # Clamp to valid range
                return max(0.0, min(1.0, calibrated))
        
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

