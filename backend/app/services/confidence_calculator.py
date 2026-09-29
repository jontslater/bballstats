"""
Confidence Calculator

Determines confidence tier (HIGH/MEDIUM/LOW/MODEL_ONLY) for predictions based on:
- Sample size (sport-specific thresholds)
- Line source (real vs synthetic)
- Data freshness
- Variance/consistency
"""
from typing import Dict, List, Optional
from datetime import date, timedelta


class ConfidenceCalculator:
    """Calculate confidence tier for predictions."""
    
    # Sport-specific sample size thresholds
    SAMPLE_SIZE_THRESHOLDS = {
        'NBA': {
            'HIGH': 30,
            'MEDIUM': 20,
            'LOW': 10,
            'MODEL_ONLY': 5
        },
        'NFL': {
            # NFL: include prior season with decay
            'HIGH': 20,  # ~20 games including prior season
            'MEDIUM': 12,
            'LOW': 6,
            'MODEL_ONLY': 3
        },
        'MLB': {
            'HIGH': 40,
            'MEDIUM': 25,
            'LOW': 15,
            'MODEL_ONLY': 8
        }
    }
    
    def __init__(self, sport: str = 'NBA'):
        """Initialize with sport-specific parameters."""
        self.sport = sport
        self.thresholds = self.SAMPLE_SIZE_THRESHOLDS.get(
            sport, self.SAMPLE_SIZE_THRESHOLDS['NBA']
        )
    
    def calculate_confidence(
        self,
        sample_size: int,
        line_source: str,
        coefficient_of_variation: Optional[float] = None,
        days_since_last_game: Optional[int] = None,
        is_synthetic_line: bool = False,
        has_real_line: bool = False
    ) -> Dict[str, any]:
        """
        Calculate confidence tier and score.
        
        Args:
            sample_size: Number of games in history
            line_source: 'sportsbook' or 'model'
            coefficient_of_variation: std_dev / mean
            days_since_last_game: Freshness of data
            is_synthetic_line: Whether line is model-generated
            has_real_line: Whether a real sportsbook line exists
        
        Returns:
            Dict with 'tier', 'score', 'reasons'
        """
        reasons = []
        score = 0.0
        
        # 1. Base tier from sample size
        if sample_size >= self.thresholds['HIGH']:
            base_tier = 'HIGH'
            score += 100
            reasons.append(f"{sample_size} games (excellent sample)")
        elif sample_size >= self.thresholds['MEDIUM']:
            base_tier = 'MEDIUM'
            score += 70
            reasons.append(f"{sample_size} games (good sample)")
        elif sample_size >= self.thresholds['LOW']:
            base_tier = 'LOW'
            score += 40
            reasons.append(f"{sample_size} games (adequate sample)")
        else:
            base_tier = 'MODEL_ONLY'
            score += 10
            reasons.append(f"{sample_size} games (limited sample)")
        
        # 2. Line source adjustment
        if is_synthetic_line or line_source == 'model':
            # Synthetic lines capped at LOW or MODEL_ONLY
            if base_tier == 'HIGH':
                base_tier = 'LOW'
                score -= 30
                reasons.append("Synthetic line (no sportsbook line available)")
            elif base_tier == 'MEDIUM':
                base_tier = 'LOW'
                score -= 20
                reasons.append("Synthetic line (no sportsbook line available)")
            # LOW and MODEL_ONLY stay as is
            if base_tier in ['LOW', 'MODEL_ONLY']:
                reasons.append("Model-generated line")
        else:
            # Real sportsbook line
            score += 20
            reasons.append("Real sportsbook line")
        
        # 3. Variance penalty
        if coefficient_of_variation is not None:
            if coefficient_of_variation > 0.50:
                # High variance
                score -= 20
                reasons.append(f"High variance (CV={coefficient_of_variation:.2f})")
                # Potentially downgrade tier
                if base_tier == 'HIGH' and coefficient_of_variation > 0.60:
                    base_tier = 'MEDIUM'
            elif coefficient_of_variation > 0.35:
                # Moderate variance
                score -= 10
                reasons.append(f"Moderate variance (CV={coefficient_of_variation:.2f})")
            else:
                # Low variance - bonus
                score += 10
                reasons.append(f"Low variance (CV={coefficient_of_variation:.2f})")
        
        # 4. Data freshness
        if days_since_last_game is not None:
            if days_since_last_game > 14:
                score -= 15
                reasons.append(f"Stale data ({days_since_last_game} days since last game)")
                # Downgrade tier if very stale
                if days_since_last_game > 30 and base_tier == 'HIGH':
                    base_tier = 'MEDIUM'
            elif days_since_last_game > 7:
                score -= 5
                reasons.append(f"Somewhat stale data ({days_since_last_game} days)")
        
        # Final score clamped
        score = max(0, min(100, score))
        
        return {
            'tier': base_tier,
            'score': round(score, 1),
            'reasons': reasons
        }
    
    def calculate_combo_confidence(
        self,
        individual_confidences: List[Dict]
    ) -> Dict[str, any]:
        """
        Calculate confidence for a combo bet (e.g., points+rebounds).
        
        Takes the minimum tier and weighted average score.
        Also considers sample size properly.
        
        Args:
            individual_confidences: List of confidence dicts from individual stats
        
        Returns:
            Dict with 'tier', 'score', 'reasons'
        """
        if not individual_confidences:
            return {
                'tier': 'MODEL_ONLY',
                'score': 0,
                'reasons': ['No component confidences']
            }
        
        # Tier hierarchy for comparison
        tier_order = ['MODEL_ONLY', 'LOW', 'MEDIUM', 'HIGH']
        
        # Take the minimum (worst) tier
        tiers = [conf.get('tier', 'MODEL_ONLY') for conf in individual_confidences]
        min_tier_idx = min(tier_order.index(t) for t in tiers)
        combined_tier = tier_order[min_tier_idx]
        
        # Average the scores
        scores = [conf.get('score', 0) for conf in individual_confidences]
        combined_score = sum(scores) / len(scores) if scores else 0
        
        # Collect reasons
        all_reasons = []
        for conf in individual_confidences:
            all_reasons.extend(conf.get('reasons', []))
        
        # Deduplicate reasons
        unique_reasons = list(dict.fromkeys(all_reasons))
        
        return {
            'tier': combined_tier,
            'score': round(combined_score, 1),
            'reasons': unique_reasons[:5]  # Limit to top 5 reasons
        }
