"""
Prediction Adjustments

Handles mean and variance adjustments for predictions based on contextual factors.
"""
from typing import Dict, Optional, List
from sqlalchemy import and_, or_, desc
from app.models.team_position_defense import TeamPositionDefense
from app.models.player_team_matchup import PlayerTeamMatchup
from app.services.pace_calculator import PaceCalculator
from app.services.injury_context import InjuryContext
from app.services.league_averages import LeagueAverages
from app.services.form_calculator import FormCalculator
from app.services.player_matchup_service import PlayerMatchupService
from app.services.teammate_chemistry_service import TeammateChemistryService
from app.services.advanced_analytics_service import AdvancedAnalyticsService
from app.services.situational_performance_service import SituationalPerformanceService
from app.services.motivation_service import MotivationService
from app.services.player_health_service import PlayerHealthService
from app.services.ml_ensemble_service import MLEnsembleService
from app.services.factor_weighting import FactorWeighting
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.team import Team


class PredictionAdjustments:
    """Apply contextual adjustments to predictions."""
    
    def __init__(self, db_session, team_defense_calculator=None, pace_calculator=None, injury_context=None, sport: str = 'NBA'):
        self.db = db_session
        self.sport = sport
        self.team_defense = team_defense_calculator
        self.pace_calc = pace_calculator or PaceCalculator(db_session)
        self.injury_ctx = injury_context or InjuryContext(db_session)
        self.league_avg = LeagueAverages(db_session, pace_calculator=self.pace_calc)
        self.form_calc = FormCalculator(db_session)
        self.player_matchup = PlayerMatchupService(db_session)
        self.teammate_chemistry = TeammateChemistryService(db_session)
        self.advanced_analytics = AdvancedAnalyticsService(db_session)
        self.situational_performance = SituationalPerformanceService(db_session)
        self.motivation = MotivationService(db_session)
        self.player_health = PlayerHealthService(db_session)
        self.ml_ensemble = MLEnsembleService(db_session)
    
    def clamp(self, value: float, min_val: float, max_val: float) -> float:
        """Clamp a value between min and max."""
        return max(min_val, min(max_val, value))
    
    def calculate_mean_adjustments(
        self,
        base_mean: float,
        player_id: int,
        opponent_team_id: int,
        projected_minutes: float,
        historical_avg_minutes: float,
        is_home: bool,
        player_position: Optional[str] = None,
        season_id: Optional[int] = None,
        usage_factor: Optional[float] = None,
        stat_type: str = 'points',
        game_id: Optional[int] = None,
        game_context: Optional[Dict] = None,
        is_promoted_bench_player: bool = False
    ) -> Dict[str, float]:
        """
        Calculate all mean adjustment factors.
        
        Returns:
            Dict with adjustment factors and final adjusted mean
        """
        # Minutes Factor (with foul trouble adjustment)
        minutes_factor = projected_minutes / historical_avg_minutes if historical_avg_minutes > 0 else 1.0
        minutes_factor = self.clamp(minutes_factor, 0.85, 1.20)
        
        # Apply foul trouble factor to minutes (reduces minutes if high foul risk)
        foul_trouble_factor = self._calculate_foul_trouble_factor(
            player_id, opponent_team_id, season_id
        )
        minutes_factor *= foul_trouble_factor
        
        # Pace Factor (NBA possessions only). MLB/NFL have no FGA/FTA/TO pace;
        # the old path scanned every team game — and league-average pace scanned
        # every team — on each player/stat prediction.
        if self.sport == 'NBA':
            team_pace = self.pace_calc.calculate_team_pace(opponent_team_id, season_id) or 100.0
            recent_pace = self.pace_calc.calculate_recent_team_pace(opponent_team_id, season_id, last_n_games=10)
            pace_to_use = recent_pace if recent_pace else team_pace
            league_avg_pace = self.league_avg.calculate_league_avg_pace(season_id)
            pace_factor = pace_to_use / league_avg_pace if league_avg_pace > 0 else 1.0
            pace_factor = self.clamp(pace_factor, 0.85, 1.20)
        else:
            team_pace = 100.0
            recent_pace = None
            league_avg_pace = 100.0
            pace_factor = 1.0
        
        # Defense Factor (Opponent vs Position)
        # IMPORTANT: This applies to ALL stat types (points, rebounds, assists)
        # Now includes recent defensive performance (last 10 games)
        defense_factor = 1.0
        if player_position:
            defense = self.db.query(TeamPositionDefense).filter(
                and_(
                    TeamPositionDefense.team_id == opponent_team_id,
                    TeamPositionDefense.position == player_position,
                    TeamPositionDefense.season_id == season_id
                )
            ).first()
            
            if defense:
                # Get league average for this position and stat type
                league_avg_allowed = None
                opponent_avg_allowed = None
                
                # Prefer recent form (last 10 games) if available, otherwise use season average
                if stat_type == 'points':
                    if defense.last_10_games_avg_points_allowed:
                        opponent_avg_allowed = defense.last_10_games_avg_points_allowed
                    elif defense.avg_points_allowed:
                        opponent_avg_allowed = defense.avg_points_allowed
                    
                    if opponent_avg_allowed:
                        league_avg_allowed = self.league_avg.calculate_league_avg_points_by_position(
                            player_position, season_id
                        )
                elif stat_type == 'rebounds':
                    if defense.avg_rebounds_allowed:
                        opponent_avg_allowed = defense.avg_rebounds_allowed
                        league_avg_allowed = self.league_avg.calculate_league_avg_rebounds_by_position(
                            player_position, season_id
                        )
                    
                    # ENHANCEMENT: Add team-level rebounding factors for rebounds
                    # Good defense = fewer shots = fewer total rebounds
                    # Poor defensive rebounding = more offensive rebounds for opponent
                    # Good offensive rebounding = more rebounds for player's team
                    team_rebounding_factor = self._calculate_team_rebounding_factor(
                        player_id, opponent_team_id, season_id
                    )
                    # Apply team rebounding factor in addition to position defense
                    if opponent_avg_allowed and league_avg_allowed and league_avg_allowed > 0:
                        # Combine position defense with team rebounding
                        position_defense_factor = opponent_avg_allowed / league_avg_allowed
                        defense_factor = position_defense_factor * team_rebounding_factor
                    else:
                        # If no position defense data, use team rebounding alone
                        defense_factor = team_rebounding_factor
                elif stat_type == 'assists':
                    if defense.avg_assists_allowed:
                        opponent_avg_allowed = defense.avg_assists_allowed
                        league_avg_allowed = self.league_avg.calculate_league_avg_assists_by_position(
                            player_position, season_id
                        )
                
                # Calculate defense factor if we have both values
                if opponent_avg_allowed and league_avg_allowed and league_avg_allowed > 0:
                    # Higher opponent avg allowed = easier matchup = boost prediction
                    # Lower opponent avg allowed = tougher matchup = reduce prediction
                    base_defense_factor = opponent_avg_allowed / league_avg_allowed

                    # ENHANCEMENT: Apply stat-specific defense weighting
                    # Points most affected by defense, rebounds least affected
                    if stat_type == 'points':
                        defense_weight = 1.0  # Full weight for points
                    elif stat_type == 'assists':
                        defense_weight = 0.8  # Assists moderately affected by defense
                    elif stat_type == 'rebounds':
                        defense_weight = 0.6  # Rebounds less affected by defensive scheme
                    elif stat_type == 'three_pointers_made':
                        defense_weight = 0.9  # 3s heavily affected by perimeter defense
                    else:
                        defense_weight = 0.7  # Default moderate weight

                    # Apply stat-specific weighting
                    defense_factor = 1.0 + ((base_defense_factor - 1.0) * defense_weight)
                    defense_factor = self.clamp(defense_factor, 0.80, 1.25)

        # ENHANCEMENT: Offensive Context Factor
        # Consider opponent's offensive efficiency and its impact on certain stats
        offensive_context_factor = 1.0
        if stat_type in ['rebounds', 'assists', 'three_pointers_made']:
            opponent_recent_offense = self._calculate_team_recent_offense(opponent_team_id, season_id)
            league_avg_offense = self._calculate_league_avg_offense(season_id)

            if league_avg_offense > 0 and opponent_recent_offense > 0:
                offense_strength = opponent_recent_offense / league_avg_offense

                # Stat-specific offensive context effects:
                if stat_type == 'rebounds':
                    # Better offense = more misses = more rebounds available
                    offensive_context_factor = 1.0 + ((offense_strength - 1.0) * 0.25)
                elif stat_type == 'assists':
                    # Better offense = more ball movement = more assists
                    offensive_context_factor = 1.0 + ((offense_strength - 1.0) * 0.35)
                elif stat_type == 'three_pointers_made':
                    # Better offense = more spacing = more 3-point attempts
                    offensive_context_factor = 1.0 + ((offense_strength - 1.0) * 0.20)

                offensive_context_factor = self.clamp(offensive_context_factor, 0.90, 1.10)

        # ENHANCEMENT: Lineup Context Factor
        # Consider how lineup stability and changes affect performance
        lineup_context_factor = 1.0

        # Check for lineup changes that might affect this player
        lineup_stability = self._calculate_lineup_stability_factor(
            player_id, game_id, season_id, is_promoted_bench_player
        )
        lineup_context_factor = lineup_stability

        # ENHANCEMENT: Teammate Chemistry Factor
        # Consider how teammate performance affects individual player performance
        teammate_chemistry_factor = 1.0

        if game_id:
            # Get current teammate performance projections for this game
            teammate_performance = self._get_teammate_performance_projections(
                player_id, game_id, season_id
            )

            if teammate_performance:
                teammate_chemistry_factor = self.teammate_chemistry.get_teammate_performance_multiplier(
                    player_id, teammate_performance, stat_type, season_id
                )

        # ENHANCEMENT: Advanced Analytics Factor
        # Use sophisticated NBA metrics (PER, TS%, USG%, etc.) for better predictions.
        # Skip for non-NBA: the helper N+1-scans teammate box scores per recent game.
        if self.sport == 'NBA':
            advanced_analytics_factor = self.advanced_analytics.get_advanced_performance_multiplier(
                player_id, stat_type, season_id, recent_games=10
            )
        else:
            advanced_analytics_factor = 1.0

        # ENHANCEMENT: Situational Performance Factor
        # Consider how player performs in current game situation (clutch, blowout, pace, etc.)
        situational_performance_factor = 1.0

        if game_context:
            # Extract situational context from game_context
            situational_context = self._extract_situational_context(game_context)
            situational_performance_factor = self.situational_performance.get_situational_performance_multiplier(
                player_id, stat_type, situational_context, season_id
            )

        # ENHANCEMENT: Motivation Factor
        # Consider psychological factors (playoffs, rivalries, revenge)
        motivation_factor = 1.0

        if game_id:
            motivation_factor = self.motivation.calculate_motivation_multiplier(
                player_id, game_id, season_id
            )

        # ENHANCEMENT: Player Health & Fatigue Factor
        # Consider player's physical condition, fatigue, and load management
        health_factor = 1.0

        if game_id:
            health_analysis = self.player_health.calculate_health_fatigue_factor(
                player_id, game_id, season_id, projected_minutes
            )
            health_factor = health_analysis.get('overall_factor', 1.0)

        # ENHANCEMENT: ML Ensemble Prediction Factor
        # Use machine learning models for advanced prediction calibration
        ml_factor = 1.0

        if game_id:
            try:
                # Build feature vector for current game
                feature_vector = self._build_ml_feature_vector(
                    player_id, game_id, stat_type, season_id,
                    projected_minutes, game_context
                )

                if feature_vector:
                    # Get ML prediction
                    ml_prediction = self.ml_ensemble.predict_with_ensemble(
                        player_id, stat_type, feature_vector, season_id
                    )

                    if 'prediction' in ml_prediction and 'confidence' in ml_prediction:
                        predicted_value = ml_prediction['prediction']
                        confidence = ml_prediction['confidence']

                        # Calculate adjustment factor based on ML prediction vs base prediction
                        if base_mean > 0 and predicted_value > 0:
                            ml_factor = predicted_value / base_mean

                            # Weight by confidence (higher confidence = stronger adjustment)
                            confidence_weight = 0.3 + (confidence * 0.4)  # 0.3 to 0.7
                            ml_factor = 1.0 + ((ml_factor - 1.0) * confidence_weight)

                            # Clamp to reasonable range
                            ml_factor = max(0.75, min(1.35, ml_factor))
                        else:
                            ml_factor = 1.0
                    else:
                        ml_factor = 1.0
                else:
                    ml_factor = 1.0
            except Exception:
                # If ML fails, use traditional prediction
                ml_factor = 1.0
        
        # Usage Factor (if teammate injured)
        if usage_factor is None:
            usage_factor = 1.0
        else:
            # Clamp usage factor
            usage_factor = self.clamp(usage_factor, 0.85, 1.25)
        
        # Home/Away Factor
        home_factor = 1.05 if is_home else 0.97
        
        # Rest Days Factor (will be calculated by game context calculator)
        rest_days_factor = 1.0  # Default, will be adjusted
        
        # Matchup Factor (Player vs Team History) - NEW IMPROVEMENT
        team_matchup_factor = self._calculate_matchup_factor(
            player_id, opponent_team_id, season_id, stat_type, base_mean
        )
        if team_matchup_factor is None:
            team_matchup_factor = 1.0
        
        # Comprehensive Matchup Analysis - ADVANCED IMPROVEMENT
        # Combines multiple matchup factors for superior accuracy
        comprehensive_matchup = self.player_matchup.get_comprehensive_matchup_analysis(
            player_id, opponent_team_id, stat_type, game_id, season_id
        )
        matchup_factor = comprehensive_matchup.get('overall_matchup_factor', 1.0)
        
        # Form Trend Factor (Improving/Declining) - NEW IMPROVEMENT
        form_trend_factor = self._calculate_form_trend_factor(
            player_id, season_id, stat_type
        )
        if form_trend_factor is None:
            form_trend_factor = 1.0
        
        # Streak Continuation Factor - ADVANCED IMPROVEMENT
        # Analyzes historical patterns to predict if current streaks will continue
        # Applies to all stat types, not just points
        streak_continuation_factor = 1.0

        # Calculate current streak length for this stat
        current_streak_info = self.form_calc.calculate_player_form(
            player_id, season_id, last_n_games=15
        )

        if current_streak_info and 'streak_info' in current_streak_info:
            streak_data = current_streak_info['streak_info']
            streak_length = streak_data.get('current_streak_length', 0)

            if abs(streak_length) >= 2:  # Only consider significant streaks
                continuation_analysis = self.form_calc.calculate_streak_continuation_factor(
                    player_id, stat_type, season_id, streak_length
                )
                streak_continuation_factor = continuation_analysis.get('continuation_factor', 1.0)

        # Shooting Streak Factor (Hot/Cold) - ENHANCED IMPROVEMENT
        # Uses both traditional shooting % and True Shooting % for better accuracy
        # Enhanced with streak continuation analysis
        # Only applies to points predictions
        shooting_factor = 1.0
        if stat_type == 'points':
            shooting_streak = self.form_calc.calculate_shooting_streak(
                player_id, season_id, last_n_games=10
            )
            ts_streak = self.form_calc.calculate_true_shooting_percentage(
                player_id, season_id, last_n_games=10
            )

            # Combine both factors (weight TS% more heavily as it's more accurate)
            fg_factor = shooting_streak.get('shooting_factor', 1.0) if shooting_streak else 1.0
            ts_factor = ts_streak.get('ts_factor', 1.0) if ts_streak else 1.0

            # Ensure factors are not None
            fg_factor = fg_factor if fg_factor is not None else 1.0
            ts_factor = ts_factor if ts_factor is not None else 1.0

            # Base shooting factor from percentages
            base_shooting_factor = (fg_factor * 0.4) + (ts_factor * 0.6)

            # Enhance with streak continuation if applicable
            shooting_factor = base_shooting_factor * streak_continuation_factor
        
        # Final Adjusted Mean
        # TODO: Implement weighted combination instead of simple multiplication
        # Current: All factors multiplied equally
        # Future: Use ML-optimized weights for each factor
        # For now, use simple multiplication but log for future optimization
        
        # Ensure all factors are not None before multiplication
        minutes_factor = minutes_factor if minutes_factor is not None else 1.0
        pace_factor = pace_factor if pace_factor is not None else 1.0
        defense_factor = defense_factor if defense_factor is not None else 1.0
        offensive_context_factor = offensive_context_factor if offensive_context_factor is not None else 1.0
        lineup_context_factor = lineup_context_factor if lineup_context_factor is not None else 1.0
        teammate_chemistry_factor = teammate_chemistry_factor if teammate_chemistry_factor is not None else 1.0
        advanced_analytics_factor = advanced_analytics_factor if advanced_analytics_factor is not None else 1.0
        situational_performance_factor = situational_performance_factor if situational_performance_factor is not None else 1.0
        motivation_factor = motivation_factor if motivation_factor is not None else 1.0
        health_factor = health_factor if health_factor is not None else 1.0
        ml_factor = ml_factor if ml_factor is not None else 1.0
        usage_factor = usage_factor if usage_factor is not None else 1.0
        home_factor = home_factor if home_factor is not None else 1.0
        rest_days_factor = rest_days_factor if rest_days_factor is not None else 1.0
        matchup_factor = matchup_factor if matchup_factor is not None else 1.0
        form_trend_factor = form_trend_factor if form_trend_factor is not None else 1.0
        shooting_factor = shooting_factor if shooting_factor is not None else 1.0
        streak_continuation_factor = streak_continuation_factor if streak_continuation_factor is not None else 1.0

        # CRITICAL FIX: Use weighted factor combination instead of multiplication
        # Old method multiplied all factors together, which compounds errors exponentially
        # New method applies weighted adjustments based on empirical importance
        
        factors_dict = {
            'minutes_factor': minutes_factor,
            'pace_factor': pace_factor,
            'defense_factor': defense_factor,
            'offensive_context_factor': offensive_context_factor,
            'lineup_context_factor': lineup_context_factor,
            'teammate_chemistry_factor': teammate_chemistry_factor,
            'advanced_analytics_factor': advanced_analytics_factor,
            'situational_performance_factor': situational_performance_factor,
            'motivation_factor': motivation_factor,
            'health_factor': health_factor,
            'ml_factor': ml_factor,
            'usage_factor': usage_factor,
            'home_factor': home_factor,
            'rest_days_factor': rest_days_factor,
            'matchup_factor': matchup_factor,
            'form_trend_factor': form_trend_factor,
            'shooting_factor': shooting_factor,
            'streak_continuation_factor': streak_continuation_factor,
        }
        
        # Apply weighted factors
        weighted_result = FactorWeighting.apply_weighted_factors(base_mean, factors_dict)
        adjusted_mean = weighted_result['adjusted_value']
        
        # Apply interaction effects (e.g., rest days + tough defense compounds)
        adjusted_mean = FactorWeighting.apply_interaction_effects(adjusted_mean, factors_dict)
        
        return {
            'base_mean': base_mean,
            'minutes_factor': round(minutes_factor, 3),
            'pace_factor': round(pace_factor, 3),
            'defense_factor': round(defense_factor, 3),
            'usage_factor': round(usage_factor, 3),
            'home_factor': round(home_factor, 3),
            'rest_days_factor': round(rest_days_factor, 3),
            'matchup_factor': round(matchup_factor, 3),  # Comprehensive matchup analysis
            'streak_continuation_factor': round(streak_continuation_factor, 3),
            'offensive_context_factor': round(offensive_context_factor, 3),
            'lineup_context_factor': round(lineup_context_factor, 3),
            'teammate_chemistry_factor': round(teammate_chemistry_factor, 3),
            'advanced_analytics_factor': round(advanced_analytics_factor, 3),
            'situational_performance_factor': round(situational_performance_factor, 3),
            'motivation_factor': round(motivation_factor, 3),
            'health_factor': round(health_factor, 3),
            'ml_factor': round(ml_factor, 3),
            'form_trend_factor': round(form_trend_factor, 3),
            'shooting_factor': round(shooting_factor, 3) if stat_type == 'points' else 1.0,
            'foul_trouble_factor': round(foul_trouble_factor, 3),  # Already applied to minutes_factor
            'adjusted_mean': round(adjusted_mean, 2)
        }
    
    def calculate_variance_adjustments(
        self,
        base_std: float,
        minutes_are_locked: bool = False,
        minutes_are_unstable: bool = False,
        usage_depends_on_others: bool = False,
        usage_is_stable: bool = False,
        blowout_risk_high: bool = False,
        sample_size: Optional[int] = None
    ) -> Dict[str, float]:
        """
        Calculate variance adjustment factors with empirical Bayes shrinkage.
        
        For small samples, we increase variance (reduce confidence) to account for
        uncertainty. This prevents overconfidence in predictions based on few games.
        
        Returns:
            Dict with volatility multipliers and final adjusted std dev
        """
        # Minutes Volatility
        if minutes_are_locked:
            minutes_volatility = 0.90
        elif minutes_are_unstable:
            minutes_volatility = 1.20
        else:
            minutes_volatility = 1.00
        
        # Usage Volatility
        if usage_depends_on_others:
            usage_volatility = 1.25
        elif usage_is_stable:
            usage_volatility = 0.90
        else:
            usage_volatility = 1.00
        
        # Blowout Risk
        blowout_volatility = 1.15 if blowout_risk_high else 1.00
        
        # Empirical Bayes shrinkage for small sample sizes
        # For small samples, increase variance (decrease confidence) to account for uncertainty
        # This prevents overconfidence in predictions from limited data
        sample_size_adjustment = 1.0
        if sample_size is not None:
            if sample_size < 10:
                # Very small sample: large variance increase (30-50%)
                # Formula: 1.0 + (target_games - actual_games) * rate
                sample_size_adjustment = 1.0 + (10 - sample_size) * 0.04  # 4% per missing game
                sample_size_adjustment = min(sample_size_adjustment, 1.50)  # Cap at 50% increase
            elif sample_size < 20:
                # Small sample: moderate variance increase (15-30%)
                sample_size_adjustment = 1.0 + (20 - sample_size) * 0.015  # 1.5% per missing game
                sample_size_adjustment = min(sample_size_adjustment, 1.30)  # Cap at 30% increase
            elif sample_size < 30:
                # Medium sample: slight variance increase (5-15%)
                sample_size_adjustment = 1.0 + (30 - sample_size) * 0.005  # 0.5% per game under 30
                sample_size_adjustment = min(sample_size_adjustment, 1.10)  # Cap at 10% increase
        
        # Final Adjusted Standard Deviation
        adjusted_std = base_std * minutes_volatility * usage_volatility * blowout_volatility * sample_size_adjustment
        
        # Cap variance (but allow higher for small samples)
        max_multiplier = 1.6 if sample_size and sample_size < 20 else 1.5
        adjusted_std = self.clamp(adjusted_std, base_std * 0.8, base_std * max_multiplier)
        
        return {
            'base_std': base_std,
            'minutes_volatility': round(minutes_volatility, 3),
            'usage_volatility': round(usage_volatility, 3),
            'blowout_volatility': round(blowout_volatility, 3),
            'sample_size_adjustment': round(sample_size_adjustment, 3) if sample_size is not None else 1.0,
            'adjusted_std': round(adjusted_std, 2)
        }
    
    def reconstruct_distribution(
        self,
        adjusted_mean: float,
        adjusted_std: float
    ) -> Dict[str, float]:
        """
        Reconstruct distribution from adjusted mean and std dev.
        
        Uses scipy.stats.norm to calculate percentiles.
        
        Returns:
            Dict with recalculated percentiles
        """
        from scipy.stats import norm
        
        # Create normal distribution
        dist = norm(loc=adjusted_mean, scale=adjusted_std)
        
        # Recalculate percentiles
        percentiles = {
            10: round(float(dist.ppf(0.10)), 2),
            20: round(float(dist.ppf(0.20)), 2),
            25: round(float(dist.ppf(0.25)), 2),
            50: round(float(dist.ppf(0.50)), 2),  # Median
            75: round(float(dist.ppf(0.75)), 2),
            80: round(float(dist.ppf(0.80)), 2),
            85: round(float(dist.ppf(0.85)), 2),
            90: round(float(dist.ppf(0.90)), 2)
        }
        
        return percentiles
    
    def _calculate_matchup_factor(
        self,
        player_id: int,
        opponent_team_id: int,
        season_id: Optional[int],
        stat_type: str,
        base_mean: float
    ) -> float:
        """
        Calculate adjustment factor based on player's historical performance vs. opponent team.
        
        Returns:
            Multiplier factor (0.85 to 1.25)
        """
        if not season_id:
            return 1.0
        
        # Get matchup history
        matchup = self.db.query(PlayerTeamMatchup).filter(
            and_(
                PlayerTeamMatchup.player_id == player_id,
                PlayerTeamMatchup.opponent_team_id == opponent_team_id,
                PlayerTeamMatchup.season_id == season_id,
                PlayerTeamMatchup.games_played >= 3  # Need at least 3 games for reliability
            )
        ).first()
        
        if not matchup:
            return 1.0  # No matchup data, no adjustment
        
        # Get the relevant stat average from matchup
        matchup_avg = None
        if stat_type == 'points':
            matchup_avg = matchup.avg_points
        elif stat_type == 'rebounds':
            matchup_avg = matchup.avg_rebounds
        elif stat_type == 'assists':
            matchup_avg = matchup.avg_assists
        
        if not matchup_avg or base_mean == 0:
            return 1.0
        
        # Calculate factor: if player averages 20% more vs this team, boost by 20%
        matchup_factor = matchup_avg / base_mean
        
        # Clamp to reasonable range (15% boost max, 15% penalty max)
        matchup_factor = self.clamp(matchup_factor, 0.85, 1.15)
        
        return matchup_factor
    
    def _calculate_form_trend_factor(
        self,
        player_id: int,
        season_id: Optional[int],
        stat_type: str
    ) -> float:
        """
        Calculate adjustment factor based on recent form trend (improving/declining).
        
        TODO: Implement time-weighted form (exponential decay)
        - More recent games should be weighted more heavily
        - Current: Equal weight for all recent games
        - Future: Game 1 day ago = 1.0, 5 days = 0.8, 10 days = 0.6, etc.
        
        Returns:
            Multiplier factor (0.95 to 1.05)
        """
        try:
            # Get recent form data (now includes time-weighted averages)
            form_data = self.form_calc.calculate_player_form(
                player_id=player_id,
                season_id=season_id,
                last_n_games=15
            )
            
            if form_data.get('games', 0) < 10:
                return 1.0  # Not enough data
            
            # Use time-weighted average for more accurate recent form
            # This gives more weight to very recent games
            tw_avg = None
            season_avg = None
            
            if stat_type == 'points':
                tw_avg = form_data.get('tw_avg_points')
                season_avg = form_data.get('avg_points')
            elif stat_type == 'rebounds':
                tw_avg = form_data.get('tw_avg_rebounds')
                season_avg = form_data.get('avg_rebounds')
            elif stat_type == 'assists':
                tw_avg = form_data.get('tw_avg_assists')
                season_avg = form_data.get('avg_assists')
            
            # Fallback to last 5 vs last 10 if time-weighted not available
            if not tw_avg or not season_avg:
                last_5_avg = form_data.get('last_5_avg_points')
                last_10_avg = form_data.get('last_10_avg_points')
                
                if not last_5_avg or not last_10_avg:
                    return 1.0
                
                trend_ratio = last_5_avg / last_10_avg if last_10_avg > 0 else 1.0
            else:
                # Compare time-weighted recent average vs overall average
                # This is more accurate as it weights recent games more heavily
                trend_ratio = tw_avg / season_avg if season_avg > 0 else 1.0
            
            # Apply trend factor
            # If improving (last 5 > last 10): boost by up to 5%
            # If declining (last 5 < last 10): penalty by up to 5%
            if trend_ratio > 1.05:  # Improving significantly (>5%)
                form_factor = 1.05
            elif trend_ratio > 1.02:  # Improving slightly (2-5%)
                form_factor = 1.02
            elif trend_ratio < 0.95:  # Declining significantly (>5%)
                form_factor = 0.95
            elif trend_ratio < 0.98:  # Declining slightly (2-5%)
                form_factor = 0.98
            else:  # Stable (within 2%)
                form_factor = 1.0
            
            return form_factor
        except Exception as e:
            # If form calculation fails, return neutral factor
            print(f"Warning: Could not calculate form trend for player {player_id}: {e}")
            return 1.0
    
    def _calculate_foul_trouble_factor(
        self,
        player_id: int,
        opponent_team_id: int,
        season_id: Optional[int] = None
    ) -> float:
        """
        Calculate foul trouble risk factor.
        
        Returns:
            Adjustment factor (0.95 to 1.0) - affects minutes projection
        """
        from app.models.season import Season
        
        if self.sport != 'NBA':
            return 1.0

        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return 1.0
            season_id = season.season_id
        
        # Get player's average fouls per game
        player_stats = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).all()
        
        if len(player_stats) < 10:
            return 1.0
        
        # Filter out None values and ensure we have valid data
        valid_fouls = [s.personal_fouls for s in player_stats if s.personal_fouls is not None]
        if not valid_fouls:
            return 1.0  # No foul data, no adjustment
        avg_fouls = sum(valid_fouls) / len(valid_fouls)
        
        # Get opponent's ability to draw fouls (opponent FTA per game)
        opponent_games = self.db.query(Game).filter(
            and_(
                or_(
                    Game.home_team_id == opponent_team_id,
                    Game.away_team_id == opponent_team_id
                ),
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        ).all()
        
        if len(opponent_games) < 10:
            return 1.0
        
        # Calculate opponent's average FTA (free throws attempted = drawing fouls)
        total_opponent_fta = 0
        for game in opponent_games:
            # Get opponent's stats for this game
            opponent_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.team_id == opponent_team_id
                )
            ).all()
            
            game_fta = sum(s.free_throws_attempted or 0 for s in opponent_stats)
            total_opponent_fta += game_fta
        
        avg_opponent_fta = total_opponent_fta / len(opponent_games)
        
        # League average FTA is around 20-25 per game
        league_avg_fta = 22.5
        
        # High foul risk if:
        # 1. Player averages 3.5+ fouls per game (prone to fouling)
        # 2. Opponent draws above-average fouls (high FTA)
        foul_risk = 0
        
        if avg_fouls >= 3.5:
            foul_risk += 1
        if avg_opponent_fta > league_avg_fta * 1.1:  # 10% above league average
            foul_risk += 1
        
        # Apply minutes reduction based on foul risk
        if foul_risk >= 2:  # High risk
            return 0.95  # 5% minutes reduction
        elif foul_risk == 1:  # Medium risk
            return 0.98  # 2% minutes reduction
        else:
            return 1.0  # Low risk
    
    def _calculate_team_rebounding_factor(
        self,
        player_id: int,
        opponent_team_id: int,
        season_id: Optional[int] = None
    ) -> float:
        """
        Calculate rebounding adjustment factor based on team-level rebounding rates.
        
        Factors considered:
        1. Opponent's defensive rebounding ability (DRB%) - affects offensive rebounds
        2. Opponent's offensive rebounding ability (ORB%) - affects defensive rebounds
        3. Player's team's offensive rebounding ability - affects their offensive rebounds
        4. How good defense affects total rebounds (fewer shots = fewer rebounds)
        
        Returns:
            Multiplier factor (0.90 to 1.15)
        """
        from app.models.season import Season
        from app.models.player import Player
        
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return 1.0
            season_id = season.season_id
        
        # Get player's team
        player = self.db.query(Player).filter(Player.player_id == player_id).first()
        if not player or not player.current_team_id:
            return 1.0
        
        player_team_id = player.current_team_id
        
        # Calculate team rebounding rates from game stats
        # Get all games for both teams this season
        team_games = self.db.query(Game).filter(
            and_(
                or_(
                    Game.home_team_id == opponent_team_id,
                    Game.away_team_id == opponent_team_id
                ),
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        ).all()
        
        player_team_games = self.db.query(Game).filter(
            and_(
                or_(
                    Game.home_team_id == player_team_id,
                    Game.away_team_id == player_team_id
                ),
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        ).all()
        
        if len(team_games) < 10 or len(player_team_games) < 10:
            return 1.0  # Not enough data
        
        # Calculate opponent's defensive rebounding rate (DRB%)
        # DRB% = defensive rebounds / (defensive rebounds + opponent offensive rebounds)
        opponent_total_drb = 0
        opponent_total_orb_allowed = 0
        
        for game in team_games:
            # Get opponent's defensive rebounds (they're the team)
            opponent_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.team_id == opponent_team_id
                )
            ).all()
            
            game_drb = sum(s.defensive_rebounds or 0 for s in opponent_stats)
            opponent_total_drb += game_drb
            
            # Get opponent's offensive rebounds allowed (other team's offensive rebounds)
            other_team_id = game.away_team_id if game.home_team_id == opponent_team_id else game.home_team_id
            other_team_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.team_id == other_team_id
                )
            ).all()
            
            game_orb_allowed = sum(s.offensive_rebounds or 0 for s in other_team_stats)
            opponent_total_orb_allowed += game_orb_allowed
        
        # Calculate opponent's DRB% (higher = better defensive rebounding = fewer offensive rebounds for opponent)
        opponent_drb_rate = opponent_total_drb / (opponent_total_drb + opponent_total_orb_allowed) if (opponent_total_drb + opponent_total_orb_allowed) > 0 else 0.75
        league_avg_drb_rate = 0.75  # League average is typically around 75%
        
        # Calculate player's team's offensive rebounding rate (ORB%)
        player_team_total_orb = 0
        player_team_total_drb_allowed = 0
        
        for game in player_team_games:
            # Get player's team's offensive rebounds
            player_team_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.team_id == player_team_id
                )
            ).all()
            
            game_orb = sum(s.offensive_rebounds or 0 for s in player_team_stats)
            player_team_total_orb += game_orb
            
            # Get opponent's defensive rebounds (rebounds allowed)
            other_team_id = game.away_team_id if game.home_team_id == player_team_id else game.home_team_id
            other_team_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.team_id == other_team_id
                )
            ).all()
            
            game_drb_allowed = sum(s.defensive_rebounds or 0 for s in other_team_stats)
            player_team_total_drb_allowed += game_drb_allowed
        
        # Calculate player's team's ORB% (higher = better offensive rebounding = more rebounds for their players)
        player_team_orb_rate = player_team_total_orb / (player_team_total_orb + player_team_total_drb_allowed) if (player_team_total_orb + player_team_total_drb_allowed) > 0 else 0.25
        league_avg_orb_rate = 0.25  # League average is typically around 25%
        
        # Calculate factors
        # 1. Opponent's defensive rebounding: if they're good at DRB, fewer offensive rebounds for player's team
        opponent_drb_factor = league_avg_drb_rate / opponent_drb_rate if opponent_drb_rate > 0 else 1.0
        opponent_drb_factor = self.clamp(opponent_drb_factor, 0.95, 1.10)  # 5% penalty to 10% boost
        
        # 2. Player's team's offensive rebounding: if they're good at ORB, more rebounds for their players
        player_team_orb_factor = player_team_orb_rate / league_avg_orb_rate if league_avg_orb_rate > 0 else 1.0
        player_team_orb_factor = self.clamp(player_team_orb_factor, 0.90, 1.15)  # 10% penalty to 15% boost
        
        # 3. Good defense = fewer shots = fewer total rebounds
        # Get opponent's points allowed (proxy for defensive quality)
        opponent_points_allowed = []
        for game in team_games:
            other_team_id = game.away_team_id if game.home_team_id == opponent_team_id else game.home_team_id
            other_team_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.team_id == other_team_id
                )
            ).all()
            game_points = sum(s.points or 0 for s in other_team_stats)
            opponent_points_allowed.append(game_points)
        
        avg_points_allowed = sum(opponent_points_allowed) / len(opponent_points_allowed) if opponent_points_allowed else 110
        league_avg_points_allowed = 110  # League average
        
        # Good defense (low points allowed) = fewer shots = fewer rebounds
        # But this is nuanced - good defense might force more misses (more defensive rebounds)
        # For simplicity, we'll use a small adjustment: very good defense slightly reduces total rebounds
        defense_quality_factor = 1.0
        if avg_points_allowed < league_avg_points_allowed - 5:  # Top 10 defense
            defense_quality_factor = 0.97  # 3% reduction (fewer shots overall)
        elif avg_points_allowed > league_avg_points_allowed + 5:  # Bottom 10 defense
            defense_quality_factor = 1.03  # 3% boost (more shots = more rebounds)
        
        # Combine all factors
        # Weight: opponent DRB (30%), player team ORB (40%), defense quality (30%)
        rebounding_factor = (
            opponent_drb_factor * 0.3 +
            player_team_orb_factor * 0.4 +
            defense_quality_factor * 0.3
        )
        
        # Clamp final factor
        rebounding_factor = self.clamp(rebounding_factor, 0.90, 1.15)

        return rebounding_factor

    def _calculate_team_recent_offense(self, team_id: int, season_id: Optional[int] = None, last_n_games: int = 10) -> float:
        """
        Calculate a team's recent offensive efficiency (points per game).

        Returns:
            Average points scored per game in recent games, or 0 if no data
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return 0.0
            season_id = season.season_id

        # Get team's recent games
        team_games = self.db.query(Game).filter(
            and_(
                or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        ).order_by(desc(Game.game_date)).limit(last_n_games).all()

        if not team_games:
            return 0.0

        total_points = 0
        for game in team_games:
            # Get all player stats for this team in this game
            game_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.team_id == team_id
                )
            ).all()

            game_points = sum(s.points or 0 for s in game_stats)
            total_points += game_points

        return total_points / len(team_games) if team_games else 0.0

    def _calculate_league_avg_offense(self, season_id: Optional[int] = None) -> float:
        """
        Calculate league average offensive efficiency (points per game).

        Returns:
            League average points per game
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return 110.0  # NBA league average fallback
            season_id = season.season_id

        # Get all finished games this season
        all_games = self.db.query(Game).filter(
            and_(
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        ).all()

        if not all_games:
            return 110.0  # NBA league average fallback

        total_points = 0
        game_count = 0

        for game in all_games:
            # Count points for both teams
            home_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.team_id == game.home_team_id
                )
            ).all()
            away_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.team_id == game.away_team_id
                )
            ).all()

            home_points = sum(s.points or 0 for s in home_stats)
            away_points = sum(s.points or 0 for s in away_stats)

            total_points += home_points + away_points
            game_count += 2  # Two teams per game

        return total_points / game_count if game_count > 0 else 110.0

    def _calculate_lineup_stability_factor(
        self,
        player_id: int,
        game_id: int,
        season_id: Optional[int] = None,
        is_promoted_bench_player: bool = False
    ) -> float:
        """
        Calculate how lineup stability affects player performance.

        Args:
            player_id: Player to analyze
            game_id: Current game
            season_id: Season for analysis
            is_promoted_bench_player: Whether player was recently promoted to starter

        Returns:
            Adjustment factor based on lineup stability
        """
        from app.models.lineup import Lineup
        from datetime import timedelta

        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return 1.0
            season_id = season.season_id

        # Get current game
        current_game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not current_game:
            return 1.0

        # Check if this is a significant lineup change for the player
        thirty_days_ago = current_game.game_date - timedelta(days=30)

        # Get player's recent lineup history
        recent_lineups = self.db.query(Lineup).join(Game).filter(
            and_(
                Lineup.player_id == player_id,
                Game.season_id == season_id,
                Game.game_date >= thirty_days_ago,
                Game.game_date < current_game.game_date,
                Game.game_status == 'finished'
            )
        ).order_by(Game.game_date).all()

        if len(recent_lineups) < 5:  # Need some history
            return 1.0

        # Calculate starter consistency
        starter_games = sum(1 for l in recent_lineups if l.is_starter)
        starter_rate = starter_games / len(recent_lineups)

        # Check current game lineup status
        current_lineup = self.db.query(Lineup).filter(
            and_(
                Lineup.player_id == player_id,
                Lineup.game_id == game_id
            )
        ).first()

        is_currently_starting = current_lineup.is_starter if current_lineup else False

        # Calculate lineup stability factor
        stability_factor = 1.0

        # Promoted bench players often perform better due to increased opportunity
        if is_promoted_bench_player:
            stability_factor *= 1.08  # 8% boost for promoted players
        elif is_currently_starting and starter_rate < 0.3:
            # Starting after being a bench player - positive change
            stability_factor *= 1.05  # 5% boost for positive lineup change
        elif not is_currently_starting and starter_rate > 0.7:
            # Benched after being a starter - negative change
            stability_factor *= 0.95  # 5% penalty for negative lineup change
        elif abs(starter_rate - (1.0 if is_currently_starting else 0.0)) > 0.5:
            # Significant lineup change from recent pattern
            stability_factor *= 0.98  # Small penalty for lineup disruption

        # Clamp to reasonable range
        return self.clamp(stability_factor, 0.90, 1.15)

    def _get_teammate_performance_projections(
        self,
        player_id: int,
        game_id: int,
        season_id: Optional[int] = None
    ) -> Optional[Dict[int, Dict[str, float]]]:
        """
        Get projected performance for teammates in an upcoming game.

        Returns:
            Dict of teammate_id -> {stat_type: projected_value}
        """
        from app.models.lineup import Lineup
        from app.models.game import Game

        try:
            # Get the game and player's team
            game = self.db.query(Game).filter(Game.game_id == game_id).first()
            if not game:
                return None

            # Find player's team
            player_team_id = None
            home_lineup = self.db.query(Lineup).filter(
                and_(Lineup.game_id == game_id, Lineup.team_id == game.home_team_id)
            ).first()
            away_lineup = self.db.query(Lineup).filter(
                and_(Lineup.game_id == game_id, Lineup.team_id == game.away_team_id)
            ).first()

            if home_lineup and player_id in [p.player_id for p in self.db.query(Lineup).filter(
                and_(Lineup.game_id == game_id, Lineup.team_id == game.home_team_id)
            ).all()]:
                player_team_id = game.home_team_id
            elif away_lineup and player_id in [p.player_id for p in self.db.query(Lineup).filter(
                and_(Lineup.game_id == game_id, Lineup.team_id == game.away_team_id)
            ).all()]:
                player_team_id = game.away_team_id

            if not player_team_id:
                return None

            # Get all teammates projected to play
            teammates = self.db.query(Lineup).filter(
                and_(
                    Lineup.game_id == game_id,
                    Lineup.team_id == player_team_id,
                    Lineup.player_id != player_id
                )
            ).all()

            if not teammates:
                return None

            teammate_projections = {}

            for teammate in teammates:
                # Get recent performance for this teammate (last 5 games)
                recent_stats = self.db.query(PlayerGameStat).join(Game).filter(
                    and_(
                        PlayerGameStat.player_id == teammate.player_id,
                        Game.season_id == season_id,
                        Game.game_status == 'finished',
                        PlayerGameStat.minutes_played > 0
                    )
                ).order_by(desc(Game.game_date)).limit(5).all()

                if recent_stats:
                    # Calculate recent averages
                    total_points = sum(s.points or 0 for s in recent_stats)
                    total_rebounds = sum(s.rebounds or 0 for s in recent_stats)
                    total_assists = sum(s.assists or 0 for s in recent_stats)
                    total_threes = sum(s.three_pointers_made or 0 for s in recent_stats)
                    games_played = len(recent_stats)

                    teammate_projections[teammate.player_id] = {
                        'points': total_points / games_played,
                        'rebounds': total_rebounds / games_played,
                        'assists': total_assists / games_played,
                        'three_pointers_made': total_threes / games_played
                    }

            return teammate_projections if teammate_projections else None

        except Exception:
            # If anything fails, return None to avoid breaking predictions
            return None

    def _extract_situational_context(self, game_context: Dict) -> Dict[str, any]:
        """
        Extract situational context information from game_context for situational performance analysis.

        Args:
            game_context: Game context dictionary from game context calculator

        Returns:
            Situational context dictionary for situational performance service
        """
        situational_context = {}

        # Extract blowout information
        blowout_info = game_context.get('blowout', {})
        situational_context['is_blowout'] = blowout_info.get('blowout_risk_high', False)

        # Extract score differential if available
        team_performance = game_context.get('team_performance', {})
        situational_context['final_margin'] = team_performance.get('margin', 0)

        # Extract pace information
        pace_info = game_context.get('pace', {})
        current_pace = pace_info.get('current_pace', 100)
        situational_context['is_fast_pace'] = current_pace >= 105
        situational_context['is_slow_pace'] = current_pace <= 95

        # Extract rest information
        rest_info = game_context.get('rest', {})
        situational_context['rest_days'] = rest_info.get('rest_days', 1)

        # Extract back-to-back information
        situational_context['is_back_to_back'] = rest_info.get('is_back_to_back', False)

        # Extract clutch information (close game in late stages)
        clutch_info = game_context.get('clutch', {})
        situational_context['is_clutch'] = clutch_info.get('is_clutch_situation', False)

        # Default values for missing information
        situational_context.setdefault('is_blowout', False)
        situational_context.setdefault('final_margin', 0)
        situational_context.setdefault('is_fast_pace', False)
        situational_context.setdefault('is_slow_pace', False)
        situational_context.setdefault('rest_days', 1)
        situational_context.setdefault('is_back_to_back', False)
        situational_context.setdefault('is_clutch', False)

        return situational_context

    def _build_ml_feature_vector(
        self,
        player_id: int,
        game_id: int,
        stat_type: str,
        season_id: int,
        projected_minutes: float,
        game_context: Optional[Dict] = None
    ) -> Optional[Dict[str, float]]:
        """
        Build feature vector for ML prediction using current game context.
        """
        try:
            # Get recent games for player
            recent_games = self.db.query(PlayerGameStat, Game).join(
                Game, PlayerGameStat.game_id == Game.game_id
            ).filter(
                and_(
                    PlayerGameStat.player_id == player_id,
                    Game.season_id == season_id,
                    Game.game_date < Game.query.filter(Game.game_id == game_id).first().game_date,
                    Game.game_status == 'finished',
                    PlayerGameStat.minutes_played > 0
                )
            ).order_by(desc(Game.game_date)).limit(20).all()

            if len(recent_games) < 5:
                return None

            # Build feature vector similar to training data
            features = {}

            # Recent performance features
            recent_stats = [stat for stat, game in recent_games[:10]]
            features.update(self._extract_recent_performance_features(recent_stats, stat_type))

            # Current game context
            current_game = self.db.query(Game).filter(Game.game_id == game_id).first()
            if current_game:
                # Opponent features
                features['is_home'] = 1.0 if current_game.home_team_id else 0.0

                # Day of week
                features['is_weekend'] = 1.0 if current_game.game_date.weekday() >= 5 else 0.0

                # Health features (simplified)
                features['avg_minutes_recent'] = projected_minutes
                features['high_minute_games'] = sum(1 for stat, game in recent_games[:5]
                                                  if (stat.minutes_played or 0) >= 40)
                features['rest_days'] = game_context.get('rest_days_factor', 1.0) if game_context else 3.0

            return features

        except Exception:
            return None

    def _extract_recent_performance_features(
        self,
        recent_stats: List[PlayerGameStat],
        stat_type: str
    ) -> Dict[str, float]:
        """Extract recent performance features for ML."""
        features = {}

        # Recent averages
        for period in [3, 5, 10]:
            if len(recent_stats) >= period:
                values = [self._extract_stat_value(stat, stat_type) for stat in recent_stats[-period:]]
                features[f'avg_last_{period}'] = sum(values) / len(values)
                features[f'std_last_{period}'] = statistics.stdev(values) if len(values) > 1 else 0

        # Recent vs season comparison
        if len(recent_stats) >= 5:
            last_5_avg = sum(self._extract_stat_value(stat, stat_type) for stat in recent_stats[-5:]) / 5
            season_avg = sum(self._extract_stat_value(stat, stat_type) for stat in recent_stats) / len(recent_stats)
            features['recent_vs_season'] = last_5_avg / season_avg if season_avg > 0 else 1.0

        return features

    def _extract_stat_value(self, player_stat: PlayerGameStat, stat_type: str) -> float:
        """Extract stat value (local helper method)."""
        if stat_type == 'points':
            return player_stat.points or 0
        elif stat_type == 'rebounds':
            return (player_stat.offensive_rebounds or 0) + (player_stat.defensive_rebounds or 0)
        elif stat_type == 'assists':
            return player_stat.assists or 0
        elif stat_type == 'three_pointers_made':
            return player_stat.three_pointers_made or 0
        else:
            return 0

