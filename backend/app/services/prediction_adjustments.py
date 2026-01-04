"""
Prediction Adjustments

Handles mean and variance adjustments for predictions based on contextual factors.
"""
from typing import Dict, Optional
from sqlalchemy import and_, or_
from app.models.team_position_defense import TeamPositionDefense
from app.models.player_team_matchup import PlayerTeamMatchup
from app.services.pace_calculator import PaceCalculator
from app.services.injury_context import InjuryContext
from app.services.league_averages import LeagueAverages
from app.services.form_calculator import FormCalculator
from app.services.player_matchup_service import PlayerMatchupService
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.team import Team


class PredictionAdjustments:
    """Apply contextual adjustments to predictions."""
    
    def __init__(self, db_session, team_defense_calculator=None, pace_calculator=None, injury_context=None):
        self.db = db_session
        self.team_defense = team_defense_calculator
        self.pace_calc = pace_calculator or PaceCalculator(db_session)
        self.injury_ctx = injury_context or InjuryContext(db_session)
        self.league_avg = LeagueAverages(db_session)
        self.form_calc = FormCalculator(db_session)
        self.player_matchup = PlayerMatchupService(db_session)
    
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
        stat_type: str = 'points'
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
        
        # Pace Factor (with recent trend consideration)
        team_pace = self.pace_calc.calculate_team_pace(opponent_team_id, season_id) or 100.0
        # Get recent pace (last 10 games) if available
        recent_pace = self.pace_calc.calculate_recent_team_pace(opponent_team_id, season_id, last_n_games=10)
        
        # Use recent pace if available, otherwise use season average
        pace_to_use = recent_pace if recent_pace else team_pace
        
        # Get league average pace (calculated from actual data)
        league_avg_pace = self.league_avg.calculate_league_avg_pace(season_id)
        pace_factor = pace_to_use / league_avg_pace if league_avg_pace > 0 else 1.0
        pace_factor = self.clamp(pace_factor, 0.85, 1.20)
        
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
                    defense_factor = opponent_avg_allowed / league_avg_allowed
                    defense_factor = self.clamp(defense_factor, 0.85, 1.20)
        
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
        
        # Individual Player vs Player Matchup Factor - NEW IMPROVEMENT
        player_matchup_factor = self.player_matchup.get_matchup_adjustment(
            player_id, opponent_team_id, stat_type, season_id
        )
        if player_matchup_factor is None:
            player_matchup_factor = 1.0
        
        # Combine both matchup factors (weight team matchup more heavily)
        # Ensure factors are not None before calculation
        team_matchup_factor = team_matchup_factor if team_matchup_factor is not None else 1.0
        player_matchup_factor = player_matchup_factor if player_matchup_factor is not None else 1.0
        matchup_factor = (team_matchup_factor * 0.7) + (player_matchup_factor * 0.3)
        
        # Form Trend Factor (Improving/Declining) - NEW IMPROVEMENT
        form_trend_factor = self._calculate_form_trend_factor(
            player_id, season_id, stat_type
        )
        if form_trend_factor is None:
            form_trend_factor = 1.0
        
        # Shooting Streak Factor (Hot/Cold) - NEW IMPROVEMENT
        # Uses both traditional shooting % and True Shooting % for better accuracy
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
            
            # Weighted average: 40% FG%, 60% TS%
            shooting_factor = (fg_factor * 0.4) + (ts_factor * 0.6)
        
        # Final Adjusted Mean
        # TODO: Implement weighted combination instead of simple multiplication
        # Current: All factors multiplied equally
        # Future: Use ML-optimized weights for each factor
        # For now, use simple multiplication but log for future optimization
        
        # Ensure all factors are not None before multiplication
        minutes_factor = minutes_factor if minutes_factor is not None else 1.0
        pace_factor = pace_factor if pace_factor is not None else 1.0
        defense_factor = defense_factor if defense_factor is not None else 1.0
        usage_factor = usage_factor if usage_factor is not None else 1.0
        home_factor = home_factor if home_factor is not None else 1.0
        rest_days_factor = rest_days_factor if rest_days_factor is not None else 1.0
        matchup_factor = matchup_factor if matchup_factor is not None else 1.0
        form_trend_factor = form_trend_factor if form_trend_factor is not None else 1.0
        shooting_factor = shooting_factor if shooting_factor is not None else 1.0
        
        adjusted_mean = (base_mean * 
                        minutes_factor * 
                        pace_factor * 
                        defense_factor * 
                        usage_factor * 
                        home_factor * 
                        rest_days_factor *
                        matchup_factor *
                        form_trend_factor *
                        shooting_factor)
        
        # Note: Research shows some factors should be weighted differently:
        # - Minutes factor: High weight (1.0-1.2) - most important
        # - Defense factor: Medium-high weight (0.9-1.1)
        # - Pace factor: Medium weight (0.95-1.05)
        # - Form trend: Medium weight (0.95-1.05)
        # - Home factor: Low weight (1.0-1.05)
        # - Rest days: Low-medium weight (0.95-1.02)
        # Future improvement: Use MLOptimizer to determine optimal weights
        
        return {
            'base_mean': base_mean,
            'minutes_factor': round(minutes_factor, 3),
            'pace_factor': round(pace_factor, 3),
            'defense_factor': round(defense_factor, 3),
            'usage_factor': round(usage_factor, 3),
            'home_factor': round(home_factor, 3),
            'rest_days_factor': round(rest_days_factor, 3),
            'team_matchup_factor': round(team_matchup_factor, 3),
            'player_matchup_factor': round(player_matchup_factor, 3),
            'matchup_factor': round(matchup_factor, 3),  # Combined
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
        Calculate variance adjustment factors.
        
        TODO: Implement empirical Bayes shrinkage for small sample sizes
        - For small samples, shrink variance toward position average
        - This reduces overconfidence in small sample predictions
        
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
        # If sample size is small, increase variance (less confidence)
        sample_size_adjustment = 1.0
        if sample_size is not None:
            if sample_size < 20:
                # Small sample: increase variance by up to 20%
                # This accounts for uncertainty in small samples
                sample_size_adjustment = 1.0 + (20 - sample_size) * 0.01  # 1% per game under 20
                sample_size_adjustment = min(sample_size_adjustment, 1.20)  # Cap at 20% increase
            elif sample_size < 30:
                # Medium sample: slight increase
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

