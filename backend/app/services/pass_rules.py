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
        is_starter: bool = True,
        sport: str = 'NBA'
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
        # NFL: 5 games; MLB: 10 games; NBA: 15 games
        min_sample_size = 5 if sport == 'NFL' else (10 if sport == 'MLB' else 15)
        if sample_size < min_sample_size:
            reasons.append(f"Insufficient sample size ({sample_size} games, need ≥{min_sample_size})")
        
        # Rule 2: Minutes/playing time check
        # NFL: snaps; MLB: plate_appearances (2+) or innings_pitched (3+); NBA: minutes
        if sport == 'NFL':
            min_minutes_threshold = 5.0  # Very lenient for NFL
        elif sport == 'MLB':
            # Batters: 2+ PA; Pitchers: 3+ IP
            min_minutes_threshold = 2.0  # plate_appearances or innings_pitched proxy
        else:
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
        
        # Rule 4: Volatility check (CV > 50% - reduced from 40% to allow more players)
        # Players with CV > 50% will still be flagged as volatile but predictions will be generated
        if coefficient_of_variation and coefficient_of_variation > 0.50:
            reasons.append(f"High volatility (CV={coefficient_of_variation:.2f}, threshold: 0.50)")
        
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

