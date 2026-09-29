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
        2. Generate candidate lines on discrete grid (0.5, 1.5, 2.5, ... for counts)
        3. Calculate calibrated probability for each candidate
        4. Choose safe = highest line with p >= 0.65
        5. Choose long_shot = line with p in 0.15-0.30 range
        6. Standard = real line or mean-based line
        
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
        # Determine standard/target line
        if real_line is not None and real_line > 0:
            standard_line = real_line
            line_source = 'sportsbook'
            is_synthetic = False
        else:
            # Shrink mean if league data available
            if league_mean is not None:
                shrunk_mean, _ = self.calibrator._shrink_mean_toward_prior(
                    adjusted_mean, sample_size, league_mean, league_std or adjusted_std
                )
            else:
                shrunk_mean = adjusted_mean
            
            # Round to nearest half-integer for discrete grid
            standard_line = round(shrunk_mean * 2) / 2
            line_source = 'model'
            is_synthetic = True
        
        # Calculate probability for standard line
        standard_data = self.calibrator.calculate_probability_for_line(
            standard_line, adjusted_mean, adjusted_std, sample_size, stat_type,
            league_mean, league_std
        )
        
        # Generate candidate lines on discrete grid
        # Range: 0.5 to 2x mean, step by 0.5
        max_line = max(adjusted_mean * 2, standard_line + 10)
        candidates = [x * 0.5 for x in range(1, int(max_line * 2) + 1)]
        
        # Find safe line: highest line with p >= 0.65
        safe_line = None
        safe_probability = None
        for line in sorted(candidates, reverse=True):
            prob_data = self.calibrator.calculate_probability_for_line(
                line, adjusted_mean, adjusted_std, sample_size, stat_type,
                league_mean, league_std
            )
            if prob_data['probability'] >= 0.65:
                safe_line = line
                safe_probability = prob_data['probability']
                break
        
        # If no safe line found, use a very low line
        if safe_line is None:
            safe_line = max(0.5, standard_line * 0.5)
            safe_data = self.calibrator.calculate_probability_for_line(
                safe_line, adjusted_mean, adjusted_std, sample_size, stat_type,
                league_mean, league_std
            )
            safe_probability = safe_data['probability']
        
        # Find long shot line: line with p in 0.15-0.30 range (prefer ~0.20)
        long_shot_line = None
        long_shot_probability = None
        best_distance = float('inf')
        target_prob = 0.20
        
        for line in candidates:
            if line <= standard_line:
                continue  # Long shot should be harder than standard
            
            prob_data = self.calibrator.calculate_probability_for_line(
                line, adjusted_mean, adjusted_std, sample_size, stat_type,
                league_mean, league_std
            )
            prob = prob_data['probability']
            
            if 0.15 <= prob <= 0.30:
                distance = abs(prob - target_prob)
                if distance < best_distance:
                    best_distance = distance
                    long_shot_line = line
                    long_shot_probability = prob
        
        # If no long shot found, use a high line
        if long_shot_line is None:
            long_shot_line = standard_line + max(3, adjusted_std)
            long_shot_data = self.calibrator.calculate_probability_for_line(
                long_shot_line, adjusted_mean, adjusted_std, sample_size, stat_type,
                league_mean, league_std
            )
            long_shot_probability = long_shot_data['probability']
        
        return {
            'safe_line': round(safe_line, 1),
            'safe_probability': safe_probability,
            'standard_line': round(standard_line, 1),
            'standard_probability': standard_data['probability'],
            'long_shot_line': round(long_shot_line, 1),
            'long_shot_probability': long_shot_probability,
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
