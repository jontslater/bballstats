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
        days_since_last_game: Optional[int] = None
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
        
        # Rule 4: Volatility check (CV > 50%)
        if coefficient_of_variation and coefficient_of_variation > 0.50:
            reasons.append(f"High volatility (CV={coefficient_of_variation:.2f}, threshold: 0.50)")
        
        # Rule 5: Injury uncertainty
        if has_injury_uncertainty:
            reasons.append("Uncertainty due to injuries or lineup changes")
        
        should_pass = len(reasons) > 0
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

