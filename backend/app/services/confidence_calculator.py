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
        has_real_line: bool = False,
        edge_over_base_rate: Optional[float] = None
    ) -> Dict[str, any]:
        """
        Calculate confidence tier and score.
        
        Tier is capped by synthetic lines (MODEL_ONLY/LOW max).
        Score varies based on sample size, variance, freshness, and edge.
        
        Args:
            sample_size: Number of games in history
            line_source: 'sportsbook' or 'model'
            coefficient_of_variation: std_dev / mean
            days_since_last_game: Freshness of data
            is_synthetic_line: Whether line is model-generated
            has_real_line: Whether a real sportsbook line exists
            edge_over_base_rate: Probability advantage over league average
        
        Returns:
            Dict with 'tier', 'score', 'reasons'
        """
        reasons = []
        score = 0.0
        
        # 1. Base tier from sample size (for tier determination only)
        if sample_size >= self.thresholds['HIGH']:
            base_tier = 'HIGH'
        elif sample_size >= self.thresholds['MEDIUM']:
            base_tier = 'MEDIUM'
        elif sample_size >= self.thresholds['LOW']:
            base_tier = 'LOW'
        else:
            base_tier = 'MODEL_ONLY'
        
        # 2. Cap tier by line source (synthetic lines max LOW/MODEL_ONLY)
        if is_synthetic_line or line_source == 'model':
            if base_tier in ['HIGH', 'MEDIUM']:
                final_tier = 'LOW'
                reasons.append("Model-generated line (no sportsbook line)")
            else:
                final_tier = base_tier
                reasons.append("Model-generated line")
        else:
            final_tier = base_tier
            reasons.append("Real sportsbook line")
        
        # 3. Sample size note
        if sample_size >= self.thresholds['HIGH']:
            reasons.append(f"{sample_size} games (excellent sample)")
        elif sample_size >= self.thresholds['MEDIUM']:
            reasons.append(f"{sample_size} games (good sample)")
        elif sample_size >= self.thresholds['LOW']:
            reasons.append(f"{sample_size} games (adequate sample)")
        else:
            reasons.append(f"{sample_size} games (limited sample)")
        
        # 4. Calculate numeric score (independent of tier caps)
        # Base score from sample size (granular, not just tier)
        score += min(sample_size * 2.0, 80)  # 0-80 range based on games
        
        # Edge bonus/penalty
        if edge_over_base_rate is not None:
            if edge_over_base_rate > 0.10:
                score += 15
                reasons.append(f"Strong edge over base rate (+{edge_over_base_rate:.1%})")
            elif edge_over_base_rate > 0.05:
                score += 10
            elif edge_over_base_rate < -0.05:
                score -= 10
                reasons.append(f"Below base rate ({edge_over_base_rate:.1%})")
        
        # Variance adjustment
        if coefficient_of_variation is not None:
            if coefficient_of_variation > 0.50:
                score -= 15
                reasons.append(f"High volatility (CV={coefficient_of_variation:.2f})")
            elif coefficient_of_variation > 0.35:
                score -= 8
            else:
                score += 5
        
        # Freshness
        if days_since_last_game is not None:
            if days_since_last_game > 14:
                score -= 10
                reasons.append(f"Stale data ({days_since_last_game} days)")
            elif days_since_last_game > 7:
                score -= 5
        
        # Final score clamped
        score = max(0, min(100, score))
        
        return {
            'tier': final_tier,
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
