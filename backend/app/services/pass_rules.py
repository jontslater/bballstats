"""
Pass Rules

Determines when to pass on a bet (not recommend it).
"""
from typing import Optional, Dict
from app.services.confidence_calculator import ConfidenceCalculator


class PassRules:
    """Evaluate whether to pass on a prediction."""
    
    def __init__(self, sport: str = 'NBA'):
        """Initialize with sport-specific configuration."""
        self.sport = sport
        self.confidence_calc = ConfidenceCalculator(sport)
    
    def evaluate_pass(
        self,
        sample_size: int,
        projected_minutes: float,
        usage_change: Optional[float] = None,
        coefficient_of_variation: Optional[float] = None,
        has_injury_uncertainty: bool = False,
        blowout_risk_high: bool = False,
        is_starter: bool = True,
        line_source: str = 'model',
        is_synthetic_line: bool = True,
        days_since_last_game: Optional[int] = None,
        stat_type: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Evaluate if we should pass on this prediction.
        
        Args:
            sample_size: Number of historical games
            projected_minutes: Projected minutes for this game
            usage_change: Change in usage rate (as decimal, e.g., 0.25 for 25%)
            coefficient_of_variation: CV = std_dev / mean
            has_injury_uncertainty: Whether there's uncertainty due to injuries
            blowout_risk_high: Whether blowout risk is high
            is_starter: Whether player is a starter
            line_source: 'sportsbook' or 'model'
            is_synthetic_line: Whether line is model-generated
            days_since_last_game: Days since player's last game
            stat_type: Type of stat for sport-specific CV thresholds
        
        Returns:
            Dict with 'should_pass' (bool), 'reason' (str or None), 'confidence_level', 'confidence_data'
        """
        reasons = []
        
        # Rule 1: Sample size check
        # NFL: 3 games minimum; MLB: 8 games; NBA: 10 games
        min_sample_size = 3 if self.sport == 'NFL' else (8 if self.sport == 'MLB' else 10)
        if sample_size < min_sample_size:
            reasons.append(f"Insufficient sample size ({sample_size} games, need ≥{min_sample_size})")
        
        # Rule 2: Minutes/playing time check
        if self.sport == 'NFL':
            min_minutes_threshold = 5.0  # Snaps/touches threshold
        elif self.sport == 'MLB':
            min_minutes_threshold = 2.0  # PA or IP threshold
        else:  # NBA
            min_minutes_threshold = 16 if (blowout_risk_high and is_starter) else 18
            if not blowout_risk_high and not is_starter:
                min_minutes_threshold = 18
        
        if projected_minutes < min_minutes_threshold:
            reasons.append(f"Low projected minutes ({projected_minutes:.1f}, need ≥{min_minutes_threshold})")
        
        # Rule 3: Usage change check
        if usage_change and abs(usage_change) > 0.25:
            reasons.append(f"Large usage change ({usage_change*100:.1f}%, threshold: 25%)")
        
        # Rule 4: Volatility check - USE SPORT/STAT-APPROPRIATE THRESHOLDS
        # MLB count stats (hits, HRs) naturally have high CV due to Poisson-like distribution
        # Don't penalize them with NBA-style CV thresholds
        if coefficient_of_variation and coefficient_of_variation > 0:
            cv_threshold = self._get_cv_threshold(stat_type)
            if coefficient_of_variation > cv_threshold:
                reasons.append(f"High volatility (CV={coefficient_of_variation:.2f}, threshold: {cv_threshold:.2f})")
        
        # Rule 5: Injury uncertainty
        if has_injury_uncertainty:
            reasons.append("Uncertainty due to injuries or lineup changes")
        
        # Don't mark as should_pass - just note the reasons
        # Let confidence system handle degradation
        should_pass = False  # Changed: never hard-block, only lower confidence
        reason = "; ".join(reasons) if reasons else None
        
        # Calculate confidence using the new confidence calculator
        confidence_data = self.confidence_calc.calculate_confidence(
            sample_size=sample_size,
            line_source=line_source,
            coefficient_of_variation=coefficient_of_variation,
            days_since_last_game=days_since_last_game,
            is_synthetic_line=is_synthetic_line,
            has_real_line=(line_source == 'sportsbook')
        )
        
        return {
            'should_pass': should_pass,
            'reason': reason,
            'confidence_level': confidence_data['tier'],
            'confidence_data': confidence_data
        }
    
    def _get_cv_threshold(self, stat_type: Optional[str]) -> float:
        """
        Get sport/stat-appropriate CV threshold.
        
        MLB count stats naturally have high CV due to binomial/Poisson distribution.
        Don't use NBA-style 0.50 threshold for everything.
        """
        if self.sport == 'MLB':
            # MLB stats have naturally high variance
            mlb_thresholds = {
                'hits': 1.2,  # Hits are very variable (0-4 per game)
                'home_runs': 2.0,  # Home runs are rare events
                'total_bases': 1.5,  # Also quite variable
                'rbis': 1.5,
                'strikeouts': 1.2,  # For pitchers
            }
            return mlb_thresholds.get(stat_type, 1.0)
        elif self.sport == 'NFL':
            # NFL also has high variance
            return 0.80
        else:  # NBA
            return 0.50
    
    def _calculate_confidence(sample_size: int, reasons: list, sport: str = 'NBA') -> str:
        """
        DEPRECATED: Use ConfidenceCalculator instead.
        
        Kept for backward compatibility only.
        
        Returns:
            'HIGH', 'MEDIUM', 'LOW', or 'MODEL_ONLY'
        """
        if len(reasons) > 0:
            return 'LOW'
        
        # Sport-specific thresholds
        if sport == 'NFL':
            if sample_size >= 20:
                return 'HIGH'
            elif sample_size >= 12:
                return 'MEDIUM'
            else:
                return 'LOW'
        elif sport == 'MLB':
            if sample_size >= 40:
                return 'HIGH'
            elif sample_size >= 25:
                return 'MEDIUM'
            else:
                return 'LOW'
        else:  # NBA
            if sample_size >= 30:
                return 'HIGH'
            elif sample_size >= 20:
                return 'MEDIUM'
            else:
                return 'LOW'
    
    @staticmethod
    def calculate_volatility_level(coefficient_of_variation: Optional[float]) -> str:
        """
        Determine volatility level from CV.
        
        Returns:
            'LOW', 'MEDIUM', or 'HIGH'
        """
        if coefficient_of_variation is None:
            return 'MEDIUM'
        
        if coefficient_of_variation < 0.20:
            return 'LOW'
        elif coefficient_of_variation < 0.35:
            return 'MEDIUM'
        else:
            return 'HIGH'

