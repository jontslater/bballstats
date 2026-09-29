"""
Factor Weighting System

Applies weighted combination of adjustment factors instead of simple multiplication.
This prevents factor compounding and allows proper relative importance.
"""
from typing import Dict, Optional
import numpy as np


class FactorWeighting:
    """
    Weighted factor combination for predictions.
    
    Instead of multiplying all factors together (which compounds errors),
    we apply a weighted combination where each factor's impact is controlled.
    """
    
    # Factor weights based on empirical importance
    # Higher weight = more impact on final prediction
    FACTOR_WEIGHTS = {
        # Core factors (highest impact)
        'minutes_factor': 1.00,      # Playing time is most important
        'defense_factor': 0.85,      # Opponent defense very important
        'usage_factor': 0.75,        # Usage rate important for volume stats
        
        # Secondary factors (medium-high impact)
        'pace_factor': 0.65,         # Game pace affects opportunities
        'matchup_factor': 0.60,      # Historical matchup performance
        'form_trend_factor': 0.55,   # Recent form trend
        
        # Contextual factors (medium impact)
        'advanced_analytics_factor': 0.50,
        'teammate_chemistry_factor': 0.45,
        'lineup_context_factor': 0.45,
        'situational_performance_factor': 0.45,
        
        # Secondary contextual (lower impact)
        'offensive_context_factor': 0.35,
        'motivation_factor': 0.35,
        'health_factor': 0.40,
        'ml_factor': 0.40,
        'shooting_factor': 0.35,
        'streak_continuation_factor': 0.30,
        
        # Minimal factors (small adjustments)
        'home_factor': 0.25,         # Home court has small effect
        'rest_days_factor': 0.30,    # Rest days matter but not huge
    }
    
    @staticmethod
    def apply_weighted_factors(base_value: float, factors: Dict[str, float]) -> Dict[str, float]:
        """
        Apply weighted combination of factors to base value.
        
        Instead of: adjusted = base * f1 * f2 * f3 * ... (compounds errors)
        We use: adjusted = base * (1 + Σ(weight_i * (factor_i - 1)))
        
        This ensures:
        - Important factors (minutes, defense) have strong impact
        - Minor factors (home court) have small impact
        - Factors don't compound exponentially
        
        Args:
            base_value: Base prediction value
            factors: Dict of factor_name -> factor_value
            
        Returns:
            Dict with adjusted_value and breakdown
        """
        # Calculate weighted adjustment
        weighted_adjustment = 0.0
        factor_contributions = {}
        
        for factor_name, factor_value in factors.items():
            # Get weight for this factor (default 0.5 if unknown)
            weight = FactorWeighting.FACTOR_WEIGHTS.get(factor_name, 0.5)
            
            # Calculate contribution: weight * (factor - 1.0)
            # If factor = 1.0, no change
            # If factor > 1.0, positive adjustment
            # If factor < 1.0, negative adjustment
            contribution = weight * (factor_value - 1.0)
            weighted_adjustment += contribution
            
            factor_contributions[factor_name] = {
                'factor_value': factor_value,
                'weight': weight,
                'contribution': contribution,
                'percentage_impact': contribution * 100  # As percentage
            }
        
        # Apply weighted adjustment to base value
        # Final = base * (1 + weighted_adjustment)
        adjusted_value = base_value * (1.0 + weighted_adjustment)
        
        # Clamp to reasonable range (prevent extreme adjustments)
        # Allow -30% to +50% total adjustment
        min_adjusted = base_value * 0.70
        max_adjusted = base_value * 1.50
        adjusted_value = max(min_adjusted, min(max_adjusted, adjusted_value))
        
        # Avoid division by zero
        if base_value > 0:
            total_adjustment_pct = (adjusted_value / base_value - 1.0) * 100
        else:
            total_adjustment_pct = 0.0
        
        return {
            'adjusted_value': adjusted_value,
            'base_value': base_value,
            'total_adjustment_pct': total_adjustment_pct,
            'weighted_adjustment': weighted_adjustment,
            'factor_contributions': factor_contributions
        }
    
    @staticmethod
    def apply_interaction_effects(
        base_value: float,
        factors: Dict[str, float],
        interactions: Optional[Dict[str, tuple]] = None
    ) -> float:
        """
        Apply interaction effects between factors.
        
        Some factors interact (e.g., rest days + tough defense is worse than either alone).
        
        Args:
            base_value: Base prediction value
            factors: Dict of factor values
            interactions: Optional dict of interaction terms
            
        Returns:
            Adjusted value with interaction effects
        """
        if interactions is None:
            # Default interactions
            interactions = {
                'rest_defense': ('rest_days_factor', 'defense_factor', -0.05),
                'pace_usage': ('pace_factor', 'usage_factor', 0.03),
                'minutes_usage': ('minutes_factor', 'usage_factor', 0.04),
            }
        
        interaction_adjustment = 0.0
        
        for interaction_name, (factor1_name, factor2_name, interaction_weight) in interactions.items():
            if factor1_name in factors and factor2_name in factors:
                factor1 = factors[factor1_name]
                factor2 = factors[factor2_name]
                
                # Interaction term: (f1 - 1) * (f2 - 1) * weight
                # This captures synergistic effects
                interaction = (factor1 - 1.0) * (factor2 - 1.0) * interaction_weight
                interaction_adjustment += interaction
        
        # Apply interaction adjustment
        adjusted_value = base_value * (1.0 + interaction_adjustment)
        
        return adjusted_value


class TimeWeightedCalculator:
    """
    Time-weighted calculations for recent form.
    
    More recent games should have more weight than older games.
    """
    
    @staticmethod
    def exponential_decay_weights(num_games: int, decay_rate: float = 0.05) -> np.ndarray:
        """
        Calculate exponential decay weights for game history.
        
        Most recent game gets weight 1.0, older games decay exponentially.
        
        Args:
            num_games: Number of games in history
            decay_rate: Rate of decay per game (default 0.05 = 5% per game)
            
        Returns:
            Array of weights (most recent first)
        """
        # Generate exponential weights
        # weights[0] = 1.0 (most recent)
        # weights[i] = exp(-decay_rate * i)
        game_indices = np.arange(num_games)
        weights = np.exp(-decay_rate * game_indices)
        
        # Normalize weights to sum to num_games (maintains scale)
        weights = weights * (num_games / weights.sum())
        
        return weights
    
    @staticmethod
    def calculate_time_weighted_mean(values: np.ndarray, decay_rate: float = 0.05) -> float:
        """
        Calculate time-weighted mean of values.
        
        Args:
            values: Array of values (most recent first)
            decay_rate: Exponential decay rate
            
        Returns:
            Time-weighted mean
        """
        if len(values) == 0:
            return 0.0
        
        weights = TimeWeightedCalculator.exponential_decay_weights(len(values), decay_rate)
        weighted_mean = np.average(values, weights=weights)
        
        return float(weighted_mean)
    
    @staticmethod
    def calculate_time_weighted_std(values: np.ndarray, decay_rate: float = 0.05) -> float:
        """
        Calculate time-weighted standard deviation.
        
        Args:
            values: Array of values (most recent first)
            decay_rate: Exponential decay rate
            
        Returns:
            Time-weighted standard deviation
        """
        if len(values) <= 1:
            return 0.0
        
        weights = TimeWeightedCalculator.exponential_decay_weights(len(values), decay_rate)
        weighted_mean = np.average(values, weights=weights)
        
        # Weighted variance: sum(weights * (values - mean)^2) / sum(weights)
        weighted_variance = np.average((values - weighted_mean)**2, weights=weights)
        weighted_std = np.sqrt(weighted_variance)
        
        return float(weighted_std)
    
    @staticmethod
    def get_stat_specific_decay_rate(stat_type: str) -> float:
        """
        Get decay rate specific to stat type.
        
        Different stats have different persistence:
        - Points: decay faster (more variable game-to-game)
        - Rebounds: decay slower (more consistent)
        - Minutes: decay slowest (most stable)
        
        Args:
            stat_type: Type of stat
            
        Returns:
            Decay rate for this stat type
        """
        decay_rates = {
            'points': 0.06,           # Points vary more, use recent form heavily
            'three_pointers_made': 0.07,  # 3P% very variable
            'assists': 0.05,          # Assists moderately consistent
            'rebounds': 0.04,         # Rebounds fairly consistent
            'minutes': 0.03,          # Minutes most stable
            'usage_rate': 0.04,       # Usage fairly stable
        }
        
        return decay_rates.get(stat_type, 0.05)  # Default 5% decay
