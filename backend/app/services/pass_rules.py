"""
Pass Rules

Determines when to pass on a bet (not recommend it).
"""
from typing import Optional, Dict


class PassRules:
    """Evaluate whether to pass on a prediction."""
    
    @staticmethod
    def evaluate_pass(
        sample_size: int,
        projected_minutes: float,
        usage_change: Optional[float] = None,
        coefficient_of_variation: Optional[float] = None,
        has_injury_uncertainty: bool = False,
        blowout_risk_high: bool = False,
        is_starter: bool = True
    ) -> Dict[str, any]:
        """
        Evaluate if we should pass on this prediction.
        
        Args:
            sample_size: Number of historical games
            projected_minutes: Projected minutes for this game
            usage_change: Change in usage rate (as decimal, e.g., 0.25 for 25%)
            coefficient_of_variation: CV = std_dev / mean
            has_injury_uncertainty: Whether there's uncertainty due to injuries
        
        Returns:
            Dict with 'should_pass' (bool) and 'reason' (str or None)
        """
        reasons = []
        
        # Rule 1: Sample size check
        if sample_size < 15:
            reasons.append(f"Insufficient sample size ({sample_size} games, need ≥15)")
        
        # Rule 2: Minutes check
        # ENHANCEMENT: Relaxed thresholds to allow more players
        # In high blowout risk games, starters may get pulled early, so be more lenient
        # Bench players in blowouts get extended minutes, so also adjust threshold
        min_minutes_threshold = 16 if (blowout_risk_high and is_starter) else 18
        if not blowout_risk_high and not is_starter:
            # Bench players in normal games - relaxed threshold
            min_minutes_threshold = 18  # Reduced from 22 to 18
        
        if projected_minutes < min_minutes_threshold:
            reasons.append(f"Low projected minutes ({projected_minutes:.1f}, need ≥{min_minutes_threshold})")
        
        # Rule 3: Usage change check
        if usage_change and abs(usage_change) > 0.25:
            reasons.append(f"Large usage change ({usage_change*100:.1f}%, threshold: 25%)")
        
        # Rule 4: Volatility check (CV > 40%)
        if coefficient_of_variation and coefficient_of_variation > 0.40:
            reasons.append(f"High volatility (CV={coefficient_of_variation:.2f}, threshold: 0.40)")
        
        # Rule 5: Injury uncertainty
        if has_injury_uncertainty:
            reasons.append("Uncertainty due to injuries or lineup changes")
        
        should_pass = len(reasons) > 0
        reason = "; ".join(reasons) if reasons else None
        
        return {
            'should_pass': should_pass,
            'reason': reason,
            'confidence_level': PassRules._calculate_confidence(sample_size, reasons)
        }
    
    @staticmethod
    def _calculate_confidence(sample_size: int, reasons: list) -> str:
        """
        Calculate confidence level based on sample size and issues.
        
        Returns:
            'HIGH', 'MEDIUM', or 'LOW'
        """
        if len(reasons) > 0:
            return 'LOW'
        
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

