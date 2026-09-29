"""
Prediction Service

Main service that generates distribution-based predictions for players.
"""
from sqlalchemy import and_
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Callable
from datetime import date, timedelta
from app.models.prediction import Prediction
from app.models.game import Game
from app.models.player import Player
from app.models.season import Season
from app.models.player_game_stat import PlayerGameStat
from app.services.distribution_engine import DistributionEngine
from app.services.prediction_adjustments import PredictionAdjustments
from app.services.pass_rules import PassRules
from app.services.redistribution_engine import RedistributionEngine
from app.services.game_context_calculator import GameContextCalculator
from app.services.bet_definitions import BetDefinitions
from app.services.lineup_service import LineupService
from app.services.injury_context import InjuryContext
from app.services.ml_optimizer import MLOptimizer
from app.services.prediction_calibration import PredictionCalibration
from app.services.value_ladder_service import ValueLadderService
from scipy.stats import norm


class PredictionService:
    """Generate distribution-based predictions."""
    
    def __init__(self, db: Session, sport: str = 'NBA'):
        """
        Initialize prediction service.
        
        Args:
            db: Database session
            sport: Sport type ('NBA' or 'NFL'). Defaults to 'NBA' for backward compatibility.
        """
        self.db = db
        self.sport = sport
        
        # Get sport config
        from app.config.sport_config import get_sport_config
        self.sport_config = get_sport_config(sport)
        
        self.dist_engine = DistributionEngine(db)
        self.adjustments = PredictionAdjustments(db)
        self.pass_rules = PassRules(sport=sport)  # Pass sport to PassRules
        self.redist_engine = RedistributionEngine(db)
        self.context_calc = GameContextCalculator(db)
        
        # Initialize new bet definitions with sport
        self.bet_defs = BetDefinitions(sport=sport)
        
        self.lineup_service = LineupService(db)
        self.injury_context = InjuryContext(db)
        self.ml_optimizer = MLOptimizer(db)
        self.calibration_service = PredictionCalibration(db)
    
    def generate_prediction(
        self,
        player_id: int,
        game_id: int,
        stat_type: str = 'points'
    ) -> Optional[Prediction]:
        """
        Generate a prediction for a player in a game.
        
        Args:
            player_id: Player ID
            game_id: Game ID
            stat_type: Type of stat ('points', 'rebounds', 'assists', 'minutes')
        
        Returns:
            Prediction object or None if prediction cannot be generated
        """
        # Get game and player
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        player = self.db.query(Player).filter(Player.player_id == player_id).first()
        
        if not game or not player:
            return None
        
        # EARLY FILTER: For upcoming games, check if player is likely to play
        if game.game_status in ['scheduled', 'in_progress']:
            # Check injury status - skip if Out, Doubtful, or Questionable
            # (Questionable players are risky and may not play)
            injury_status = self.injury_context.get_player_injury_status(player_id)
            if injury_status:
                if injury_status['status'] in ['Out', 'Doubtful', 'Questionable']:
                    return None  # Player is out or questionable, don't generate prediction
            
            # Check if player is on the correct team for this game
            if player.current_team_id not in [game.home_team_id, game.away_team_id]:
                # Player not on either team, skip silently (roster data issue)
                return None
            
            # Get blowout risk early to inform decision (needed for both scheduled and finished games)
            game_context = self.context_calc.get_game_context(game_id, player.current_team_id)
            blowout_info = game_context.get('blowout', {})
            blowout_risk_high = blowout_info.get('blowout_risk_high', False)
            blowout_risk_score = blowout_info.get('risk_score', 0.0)
            
            # Check if lineup is confirmed - if so, only generate for confirmed starters
            # UNLESS blowout risk is high, in which case bench players may get extended minutes
            team_id = game.home_team_id if player.current_team_id == game.home_team_id else game.away_team_id
            is_lineup_confirmed = self.lineup_service.is_lineup_confirmed(game_id, team_id)
            
            if is_lineup_confirmed:
                # Lineup is confirmed - check if player is a starter
                is_confirmed_starter = self.lineup_service.is_player_starter(game_id, player_id)
                
                if not is_confirmed_starter:
                    # Player is NOT a starter
                    # In high blowout risk games, bench players get extended minutes, so allow predictions
                    if blowout_risk_high and blowout_risk_score >= 0.6:
                        # High blowout risk - bench players will likely get extended minutes
                        # Allow prediction but we'll adjust minutes upward later
                        pass  # Continue with prediction generation
                    else:
                        # Normal game - bench players unlikely to have betting lines
                        return None
        else:
            # For finished games, still need game_context for rest days factor
            game_context = self.context_calc.get_game_context(game_id, player.current_team_id)
            blowout_info = game_context.get('blowout', {})
            blowout_risk_high = blowout_info.get('blowout_risk_high', False)
            blowout_risk_score = blowout_info.get('risk_score', 0.0)
        
        # Determine if player is home or away
        is_home = (game.home_team_id == player.current_team_id)
        opponent_team_id = game.away_team_id if is_home else game.home_team_id
        
        # Get season
        season_id = game.season_id
        
        # Step 1: Check if player is confirmed starter for this game
        is_confirmed_starter = self.lineup_service.is_player_starter(game_id, player_id)
        
        # Step 1.5: Check if player is a "promoted" bench player (bench player now starting due to injury)
        # This is more accurate than just checking injury status - use actual lineup data
        is_promoted_bench_player = False
        if is_confirmed_starter:
            # Player is starting - check if they normally come off the bench
            # Get their recent starter rate (last 10 games)
            from datetime import timedelta
            from app.models.lineup import Lineup
            thirty_days_ago = game.game_date - timedelta(days=30)
            
            recent_starter_count = self.db.query(Lineup).join(Game).filter(
                and_(
                    Lineup.player_id == player_id,
                    Lineup.is_starter == True,
                    Game.game_date >= thirty_days_ago,
                    Game.game_date < game.game_date,
                    Game.game_status == 'finished'
                )
            ).count()
            
            recent_total_games = self.db.query(PlayerGameStat).join(Game).filter(
                and_(
                    PlayerGameStat.player_id == player_id,
                    Game.game_date >= thirty_days_ago,
                    Game.game_date < game.game_date,
                    Game.game_status == 'finished',
                    PlayerGameStat.minutes_played > 0
                )
            ).count()
            
            # If they started in less than 30% of recent games but are starting now, they're promoted
            if recent_total_games > 0:
                starter_rate = recent_starter_count / recent_total_games
                if starter_rate < 0.30 and is_confirmed_starter:
                    is_promoted_bench_player = True
                    print(f"📈 {player.name} is a promoted bench player (starter rate: {starter_rate:.1%}, now starting)")
        
        # Step 2: Calculate base minutes based on role
        # Use last 20 games for more recent form
        # For NFL, use the same season logic as distribution (use game's season)
        # For NBA, can still use game's season for precision
        season_ids_for_minutes = [season_id]  # Use game's season (2025 for NFL)
        
        historical_avg_minutes = self.dist_engine.get_historical_avg_minutes(
            player_id,
            sport=self.sport,
            season_ids=season_ids_for_minutes,
            recent_games=20  # Use last 20 games instead of all-time
        )
        
        if not historical_avg_minutes:
            # For NFL, minutes/snaps might not be available, but we can still generate predictions
            # Set a default based on position
            if self.sport == 'NFL':
                # NFL players typically play if they're active
                # Use a default that allows predictions
                historical_avg_minutes = 30.0  # Default for NFL (snaps/minutes)
            else:
                return None
        
        # FILTER: Skip players with very low historical minutes (deep bench players)
        # For NFL, lower threshold since snaps might not be tracked
        # For MLB, use PA/IP thresholds instead of minutes
        if self.sport == 'MLB':
            # For MLB, minutes represent PA/IP depending on role
            # Minimum: 2 PA for batters or 1 IP for pitchers per game on average
            min_historical_threshold = 2.0
        elif self.sport == 'NFL':
            min_historical_threshold = 5.0
        else:  # NBA
            min_historical_threshold = 12.0
            
        if game.game_status in ['scheduled', 'in_progress']:
            if historical_avg_minutes < min_historical_threshold:
                return None  # Player rarely plays, unlikely to have betting lines
        
        # If lineup is confirmed, use role-specific baseline
        if is_confirmed_starter:
            if is_promoted_bench_player:
                # This is a bench player promoted to starter - use bench game history as baseline
                # (redistribution engine will add the increase)
                # Don't use starter-only games because they don't have many/any
                print(f"   Using bench game history as baseline for promoted starter")
            else:
                # Regular starter - get starter-specific minutes (only from games where player started)
                starter_minutes = self.dist_engine.get_historical_avg_minutes(
                    player_id,
                    sport=self.sport,
                    season_ids=season_ids_for_minutes,
                    recent_games=20,
                    only_starters=True  # Only use games where player was a starter
                )
                # Use starter minutes if available, otherwise use general average
                if starter_minutes and starter_minutes > 0:
                    historical_avg_minutes = starter_minutes
                else:
                    # No starter games found, but player is confirmed starter
                    # This might be a first-time starter - use general average but log warning
                    print(f"⚠️  {player.name} is confirmed starter but has no starter game history. Using general average.")
        
        # Calculate redistributed minutes (if injuries or promoted bench player)
        minutes_redist = self.redist_engine.calculate_redistributed_minutes(
            player_id, player.current_team_id, historical_avg_minutes
        )
        projected_minutes = minutes_redist['projected_minutes']
        
        # ENHANCEMENT: If this is a promoted bench player (now starting), 
        # apply additional minutes boost beyond normal redistribution
        # because they're getting starter minutes, not just bench + injury boost
        if is_promoted_bench_player and not minutes_redist.get('benefits_from_injury'):
            # Bench player starting but no injury benefit detected - check if normal starter is out
            # Get team's normal starters at this position (recent games)
            team_id = player.current_team_id
            player_position = player.position
            
            # Get time window for checking normal starters (use same as above)
            from datetime import timedelta
            from sqlalchemy import func
            from app.models.lineup import Lineup
            thirty_days_ago_check = game.game_date - timedelta(days=30)
            
            # Find players at same position who started more often recently
            # Get this player's starter count for comparison
            this_player_starter_count = self.db.query(Lineup).join(Game).filter(
                and_(
                    Lineup.player_id == player_id,
                    Lineup.is_starter == True,
                    Game.game_date >= thirty_days_ago_check,
                    Game.game_date < game.game_date,
                    Game.game_status == 'finished'
                )
            ).count()
            
            normal_starters = self.db.query(Lineup.player_id).join(Game).filter(
                and_(
                    Lineup.team_id == team_id,
                    Lineup.is_starter == True,
                    Game.game_date >= thirty_days_ago_check,
                    Game.game_date < game.game_date,
                    Game.game_status == 'finished'
                )
            ).group_by(Lineup.player_id).having(
                func.count(Lineup.player_id) > this_player_starter_count
            ).all()
            
            normal_starter_ids = [s[0] for s in normal_starters]
            
            # Check if any normal starters are out or not in lineup
            normal_starter_out = False
            for starter_id in normal_starter_ids:
                if starter_id == player_id:
                    continue  # Skip self
                
                # Check if normal starter is in lineup for this game
                is_in_lineup = self.lineup_service.is_player_in_lineup(game_id, starter_id)
                
                if not is_in_lineup:
                    # Normal starter is not in lineup - this bench player is their replacement
                    normal_starter_out = True
                    
                    # Get normal starter's average minutes to estimate boost
                    starter_avg_minutes = self.dist_engine.get_historical_avg_minutes(
                        starter_id,
                        sport=self.sport,
                        season_ids=season_ids_for_minutes,
                        recent_games=10,
                        only_starters=True
                    )
                    
                    if starter_avg_minutes:
                        # Boost this player's minutes by 60-80% of normal starter's minutes
                        # (they won't get 100% because some minutes go to other players)
                        minutes_boost = starter_avg_minutes * 0.70  # 70% of starter minutes
                        projected_minutes = historical_avg_minutes + minutes_boost
                        minutes_redist['minutes_increase'] = minutes_boost
                        minutes_redist['projected_minutes'] = projected_minutes
                        minutes_redist['benefits_from_injury'] = True
                        print(f"   📈 Boosted {player.name} minutes by +{minutes_boost:.1f} (replacing normal starter)")
                    break
            
            # If normal starter is out but no lineup data, still boost based on position
            if not normal_starter_out and player_position:
                # Conservative boost for promoted bench player (even without confirmed starter out)
                # They're starting, so they'll get more minutes than usual
                minutes_boost = max(5.0, historical_avg_minutes * 0.40)  # At least +5 min or 40% increase
                projected_minutes = historical_avg_minutes + minutes_boost
                minutes_redist['minutes_increase'] = minutes_boost
                minutes_redist['projected_minutes'] = projected_minutes
                print(f"   📈 Boosted {player.name} minutes by +{minutes_boost:.1f} (promoted to starter)")
        
        # Apply back-to-back adjustment using game context
        rest_days_factor = game_context.get('rest_days_factor', 1.0)
        projected_minutes *= rest_days_factor
        
        # BLOWOUT ADJUSTMENT: Adjust minutes based on blowout risk and player role
        if blowout_risk_high and blowout_risk_score >= 0.6:
            # High blowout risk game
            if is_confirmed_starter:
                # Starters: Reduce minutes (they get pulled early in blowouts)
                # Reduce by 15-25% depending on risk score
                blowout_reduction = 0.15 + (blowout_risk_score - 0.6) * 0.25  # 15-25% reduction
                projected_minutes *= (1.0 - blowout_reduction)
            else:
                # Bench players: Increase minutes (they get extended time in blowouts)
                # Increase by 20-40% depending on risk score
                blowout_increase = 0.20 + (blowout_risk_score - 0.6) * 0.50  # 20-40% increase
                projected_minutes *= (1.0 + blowout_increase)
        
        # FILTER: For upcoming games, skip players with very low projected minutes
        # Sportsbooks typically only offer lines for players expected to play 15+ minutes
        # This filters out deep bench players who won't have betting lines
        # BUT: In high blowout risk games, bench players may get extended minutes, so lower threshold
        # For NFL, lower threshold since minutes/snaps tracking might not be as precise
        # For MLB, use PA/IP thresholds
        if self.sport == 'MLB':
            # MLB: 2+ PA for batters or 1+ IP for pitchers
            min_minutes_threshold = 2.0
        elif self.sport == 'NFL':
            min_minutes_threshold = 5.0
        else:  # NBA
            min_minutes_threshold = 12 if (blowout_risk_high and blowout_risk_score >= 0.6 and not is_confirmed_starter) else 15
        
        if game.game_status in ['scheduled', 'in_progress']:
            if projected_minutes < min_minutes_threshold:
                return None  # Too few minutes, unlikely to have betting lines available
        
        # Determine minimum games threshold (lower for NFL due to data limitations)
        min_games_threshold = 5 if self.sport == 'NFL' else 15
        
        # Get base distribution
        # For NFL, use current season (2025) if available, otherwise fallback to previous seasons
        # For NBA, use the game's season
        if self.sport == 'NFL':
            # Prefer using the game's season (2025) if we have data
            # Otherwise use previous seasons as fallback
            season_ids_for_dist = [season_id]  # Use the game's season (2025)
        else:
            season_ids_for_dist = [season_id]
        
        base_dist = self.dist_engine.calculate_base_distribution(
            player_id=player_id,
            stat_type=stat_type,
            sport=self.sport,
            projected_minutes=projected_minutes,
            season_ids=season_ids_for_dist,
            min_games=min_games_threshold
        )
        
        if not base_dist or base_dist.get('mean') is None or base_dist.get('std_dev') is None:
            return None  # Can't generate prediction without valid base distribution
        
        # Handle std dev = 0 case (can happen with very consistent players)
        # Set a minimum std dev to allow predictions
        base_std = base_dist.get('std_dev', 0.0)
        if base_std == 0.0 or base_std is None:
            # Use a small percentage of mean as minimum std dev
            # For NFL, use 5% of mean as minimum
            min_std_pct = 0.05 if self.sport == 'NFL' else 0.10
            base_std = max(base_dist.get('mean', 1.0) * min_std_pct, 1.0)
            base_dist['std_dev'] = base_std
        
        # Calculate usage redistribution (leverages injury context)
        # For NFL, usage rate is less relevant, skip if not available
        historical_usage = None
        usage_redist = {'usage_change_pct': 0, 'projected_usage': None}  # Default values
        
        if self.sport == 'NBA':
            historical_usage = self.dist_engine.get_historical_usage_rate(
                player_id, season_ids=[season_id]
            )
            if historical_usage and historical_usage > 0:
                usage_redist = self.redist_engine.calculate_redistributed_usage(
                    player_id, player.current_team_id, historical_usage
                )
        
        # Calculate usage factor
        if historical_usage and historical_usage > 0 and usage_redist.get('projected_usage'):
            usage_factor = usage_redist['projected_usage'] / historical_usage
        else:
            # Default usage factor (no change)
            usage_factor = 1.0
        
        # ENHANCEMENT: Get full injury context to boost beneficiary players' stats
        # Not just minutes/usage, but also direct stat increases from injury analysis
        injury_context = self.injury_context.get_team_injury_context(player.current_team_id)
        stat_boost_from_injuries = 1.0  # Multiplier for stat increases
        
        # Check if this player benefits from injuries (beyond just minutes/usage)
        for impact_data in injury_context.get('expected_impacts', []):
            if impact_data.get('player_id') == player_id:
                # This player benefits from injuries - get stat-specific boosts
                impacts = impact_data.get('impacts', [])
                if impacts:
                    # Calculate average stat increases from historical injury impacts
                    # Only proceed if base_dist has valid mean
                    if base_dist.get('mean') is None:
                        continue
                    
                    if stat_type == 'points':
                        avg_points_increase = sum(i.get('points_increase', 0) for i in impacts) / len(impacts) if impacts else 0
                        if avg_points_increase > 0:
                            # Apply boost: if player typically gets +3 points when teammate is out,
                            # boost their mean by that amount
                            stat_boost_from_injuries = 1.0 + (avg_points_increase / max(base_dist['mean'], 1.0)) * 0.5
                    elif stat_type == 'rebounds':
                        avg_rebounds_increase = sum(i.get('rebounds_increase', 0) for i in impacts) / len(impacts) if impacts else 0
                        if avg_rebounds_increase > 0:
                            stat_boost_from_injuries = 1.0 + (avg_rebounds_increase / max(base_dist['mean'], 1.0)) * 0.5
                    elif stat_type == 'assists':
                        avg_assists_increase = sum(i.get('assists_increase', 0) for i in impacts) / len(impacts) if impacts else 0
                        if avg_assists_increase > 0:
                            stat_boost_from_injuries = 1.0 + (avg_assists_increase / max(base_dist['mean'], 1.0)) * 0.5
        
        # Step 2: Calculate mean adjustments
        # Note: foul_trouble_factor is calculated inside calculate_mean_adjustments
        # and affects minutes_factor, which is already applied
        # Ensure base_mean is not None before passing
        base_mean = base_dist.get('mean')
        if base_mean is None:
            return None  # Can't proceed without base mean
        
        mean_adjustments = self.adjustments.calculate_mean_adjustments(
            base_mean=base_mean,
            player_id=player_id,
            opponent_team_id=opponent_team_id,
            projected_minutes=projected_minutes,
            historical_avg_minutes=historical_avg_minutes,
            is_home=is_home,
            player_position=player.position,
            season_id=season_id,
            usage_factor=usage_factor,
            stat_type=stat_type,
            game_id=game_id,
            game_context=game_context,
            is_promoted_bench_player=is_promoted_bench_player
        )
        
        # Ensure adjusted_mean is not None
        if mean_adjustments.get('adjusted_mean') is None:
            return None
        
        # Get game context and apply all context factors
        game_context = self.context_calc.get_game_context(game_id, player.current_team_id)
        rest_days_factor = game_context.get('rest_days_factor', 1.0)
        relative_rest_factor = game_context.get('relative_rest_factor', 1.0)
        team_performance = game_context.get('team_performance', {})
        team_performance_factor = team_performance.get('performance_factor', 1.0)
        game_importance = game_context.get('game_importance', {})
        importance_factor = game_importance.get('importance_factor', 1.0)
        national_tv_factor = game_context.get('national_tv_factor', 1.0)
        time_of_day_factor = self.context_calc.calculate_time_of_day_factor(game_id, player_id, season_id)
        clutch_performance = self.context_calc.calculate_clutch_performance(player_id, season_id)
        clutch_factor = clutch_performance.get('clutch_factor', 1.0)
        
        mean_adjustments['rest_days_factor'] = rest_days_factor
        mean_adjustments['relative_rest_factor'] = relative_rest_factor
        mean_adjustments['team_performance_factor'] = team_performance_factor
        mean_adjustments['importance_factor'] = importance_factor
        mean_adjustments['national_tv_factor'] = national_tv_factor
        mean_adjustments['time_of_day_factor'] = time_of_day_factor
        mean_adjustments['clutch_factor'] = clutch_factor
        
        # Apply all context factors (ensure adjusted_mean is not None)
        if mean_adjustments.get('adjusted_mean') is None:
            return None  # Can't proceed if adjusted_mean is None
        
        # Ensure all factors are not None before multiplication
        rest_days_factor = rest_days_factor if rest_days_factor is not None else 1.0
        relative_rest_factor = relative_rest_factor if relative_rest_factor is not None else 1.0
        team_performance_factor = team_performance_factor if team_performance_factor is not None else 1.0
        importance_factor = importance_factor if importance_factor is not None else 1.0
        national_tv_factor = national_tv_factor if national_tv_factor is not None else 1.0
        time_of_day_factor = time_of_day_factor if time_of_day_factor is not None else 1.0
        clutch_factor = clutch_factor if clutch_factor is not None else 1.0
        
        mean_adjustments['adjusted_mean'] *= rest_days_factor
        mean_adjustments['adjusted_mean'] *= relative_rest_factor
        mean_adjustments['adjusted_mean'] *= team_performance_factor
        mean_adjustments['adjusted_mean'] *= importance_factor
        mean_adjustments['adjusted_mean'] *= national_tv_factor
        mean_adjustments['adjusted_mean'] *= time_of_day_factor
        mean_adjustments['adjusted_mean'] *= clutch_factor
        
        # ENHANCEMENT: Apply injury-based stat boost (beyond minutes/usage redistribution)
        mean_adjustments['adjusted_mean'] *= stat_boost_from_injuries
        mean_adjustments['injury_stat_boost'] = stat_boost_from_injuries
        
        # Step 3: Calculate variance adjustments
        minutes_locked = self.redist_engine.is_minutes_locked(player_id, player.current_team_id)
        minutes_unstable = not minutes_locked and projected_minutes < 25
        usage_stable = self.redist_engine.is_usage_stable(player_id, player.current_team_id)
        usage_depends_on_others = not usage_stable
        
        blowout_risk = game_context.get('blowout', {}).get('blowout_risk_high', False)
        
        # Ensure base_std is not None before passing
        base_std = base_dist.get('std_dev')
        if base_std is None:
            return None  # Can't proceed without base std dev
        
        variance_adjustments = self.adjustments.calculate_variance_adjustments(
            base_std=base_std,
            minutes_are_locked=minutes_locked,
            minutes_are_unstable=minutes_unstable,
            usage_depends_on_others=usage_depends_on_others,
            usage_is_stable=usage_stable,
            blowout_risk_high=blowout_risk,
            sample_size=base_dist.get('sample_size')  # Pass sample size for empirical Bayes
        )
        
        # Ensure adjusted_std is not None
        if variance_adjustments.get('adjusted_std') is None:
            return None
        
        # Step 4: Reconstruct distribution
        adjusted_percentiles = self.adjustments.reconstruct_distribution(
            adjusted_mean=mean_adjustments['adjusted_mean'],
            adjusted_std=variance_adjustments['adjusted_std']
        )
        
        # Step 5: Calculate bet lines using calibrated probability
        # Get league averages for this stat type (optional, for shrinkage)
        league_mean, league_std = self._get_league_averages(stat_type)
        
        # TODO: Check if real betting line exists (from betting_lines table)
        # For now, we'll pass None to synthesize from the player's distribution
        real_line = None  # self._get_real_betting_line(game_id, player_id, stat_type)
        
        bet_lines = self.bet_defs.calculate_bet_lines(
            adjusted_mean=mean_adjustments['adjusted_mean'],
            adjusted_std=variance_adjustments['adjusted_std'],
            sample_size=base_dist['sample_size'],
            stat_type=stat_type,
            real_line=real_line,
            league_mean=league_mean,
            league_std=league_std
        )
        
        # Step 6: Evaluate pass rules with new confidence calculation
        # usage_redist already calculated above
        usage_change = usage_redist.get('usage_change_pct', 0) / 100.0
        
        # Calculate days since last game
        days_since_last_game = self._get_days_since_last_game(player_id, game.game_date)
        
        pass_eval = self.pass_rules.evaluate_pass(
            sample_size=base_dist['sample_size'],
            projected_minutes=projected_minutes,
            usage_change=usage_change if usage_change > 0 else None,
            coefficient_of_variation=base_dist.get('cv'),
            has_injury_uncertainty=minutes_redist['benefits_from_injury'],
            blowout_risk_high=blowout_risk_high,
            is_starter=is_confirmed_starter,
            line_source=bet_lines['line_source'],
            is_synthetic_line=bet_lines['is_synthetic'],
            days_since_last_game=days_since_last_game,
            stat_type=stat_type  # Pass stat_type for sport-specific CV thresholds
        )
        
        # Step 7: Determine which bet types qualify using CALIBRATED probabilities
        # No more flat 0.75/0.60/0.25 - use realistic thresholds
        # Note: We ALWAYS generate all three bet types (safe, standard, long_shot) for each prediction
        # Even if a bet type doesn't qualify (low probability), we still save it so regeneration
        # updates all existing rows. The API layer will filter out unqualified bets.
        
        # CRITICAL FIX: If long_shot_line is None (probability < 5%), do NOT emit long_shot row
        qualifying_bet_types = ['safe', 'standard']
        if bet_lines['long_shot_line'] is not None and bet_lines['long_shot_probability'] is not None:
            qualifying_bet_types.append('long_shot')
        else:
            # Delete any stale long_shot prediction for this player/stat/game
            stale_long_shot = self.db.query(Prediction).filter(
                and_(
                    Prediction.player_id == player_id,
                    Prediction.game_id == game_id,
                    Prediction.stat_type == stat_type,
                    Prediction.bet_type == 'long_shot',
                    Prediction.sport == self.sport
                )
            ).first()
            if stale_long_shot:
                self.db.delete(stale_long_shot)
        
        # Skip duplicates when lines collapse to the same value
        # This prevents generating multiple rows with identical lines
        if bet_lines['safe_line'] == bet_lines['standard_line']:
            qualifying_bet_types.remove('standard')
            
            # Delete any existing stale 'standard' prediction for this player/stat/game
            stale_standard = self.db.query(Prediction).filter(
                and_(
                    Prediction.player_id == player_id,
                    Prediction.game_id == game_id,
                    Prediction.stat_type == stat_type,
                    Prediction.bet_type == 'standard',
                    Prediction.sport == self.sport
                )
            ).first()
            if stale_standard:
                self.db.delete(stale_standard)
        
        if bet_lines['safe_line'] == bet_lines['long_shot_line']:
            if 'long_shot' in qualifying_bet_types:
                qualifying_bet_types.remove('long_shot')
            
            # Delete stale long_shot if it now equals safe
            stale_long_shot = self.db.query(Prediction).filter(
                and_(
                    Prediction.player_id == player_id,
                    Prediction.game_id == game_id,
                    Prediction.stat_type == stat_type,
                    Prediction.bet_type == 'long_shot',
                    Prediction.sport == self.sport
                )
            ).first()
            if stale_long_shot:
                self.db.delete(stale_long_shot)
        
        if 'standard' in qualifying_bet_types and bet_lines['standard_line'] == bet_lines['long_shot_line']:
            if 'long_shot' in qualifying_bet_types:
                qualifying_bet_types.remove('long_shot')
            
            # Delete stale long_shot if it now equals standard
            stale_long_shot = self.db.query(Prediction).filter(
                and_(
                    Prediction.player_id == player_id,
                    Prediction.game_id == game_id,
                    Prediction.stat_type == stat_type,
                    Prediction.bet_type == 'long_shot',
                    Prediction.sport == self.sport
                )
            ).first()
            if stale_long_shot:
                self.db.delete(stale_long_shot)
        
        # Step 8: Analyze lineup context for reasoning
        lineup_context = None
        try:
            from app.services.prediction_history_helper import analyze_lineup_context
            lineup_context = analyze_lineup_context(self.db, player_id, game_id, self.sport)
        except Exception as e:
            # If lineup analysis fails, continue without it
            print(f"Warning: Lineup analysis failed for player {player_id}: {e}")
            lineup_context = None

        # Step 10: Build reasoning
        # Get team names for better explanations
        from app.models.team import Team
        opponent_team = self.db.query(Team).filter(Team.team_id == opponent_team_id).first()
        opponent_team_name = opponent_team.abbreviation if opponent_team else "Opponent"

        reasoning = self._build_reasoning(
            mean_adjustments, variance_adjustments, game_context,
            minutes_redist, pass_eval, blowout_info, is_confirmed_starter,
            projected_minutes, player.name, opponent_team_name, lineup_context
        )
        
        # Step 10: Create predictions for each qualifying bet type
        # This allows the same player to have safe, standard, AND long_shot predictions
        predictions_created = []
        
        for bet_type in qualifying_bet_types:
            # Get or create prediction for this specific bet type
            # We can have multiple predictions per player-stat combo with different bet_types
            prediction = self.db.query(Prediction).filter(
                and_(
                    Prediction.player_id == player_id,
                    Prediction.game_id == game_id,
                    Prediction.stat_type == stat_type,
                    Prediction.bet_type == bet_type,
                    Prediction.sport == self.sport
                )
            ).first()
            
            is_new = prediction is None
            if is_new:
                prediction = Prediction(
                    player_id=player_id,
                    game_id=game_id,
                    stat_type=stat_type,
                    bet_type=bet_type,
                    sport=self.sport
                )
            
            # Update prediction with all the data
            # Ensure critical values are not None before saving
            if (mean_adjustments.get('adjusted_mean') is None or 
                variance_adjustments.get('adjusted_std') is None or
                not adjusted_percentiles):
                return None  # Can't save prediction with None values
            
            prediction.distribution_mean = mean_adjustments['adjusted_mean']
            prediction.distribution_std_dev = variance_adjustments['adjusted_std']
            prediction.percentile_10 = adjusted_percentiles.get(10)
            prediction.percentile_20 = adjusted_percentiles.get(20)
            prediction.percentile_25 = adjusted_percentiles.get(25)
            prediction.percentile_50 = adjusted_percentiles.get(50)
            prediction.percentile_75 = adjusted_percentiles.get(75)
            prediction.percentile_80 = adjusted_percentiles.get(80)
            prediction.percentile_85 = adjusted_percentiles.get(85)
            prediction.percentile_90 = adjusted_percentiles.get(90)
            prediction.sample_size = base_dist.get('sample_size')
            
            # Validate lines are positive and sensible
            if (bet_lines['safe_line'] <= 0 or 
                bet_lines['standard_line'] <= 0 or 
                bet_lines['long_shot_line'] <= 0):
                # Skip this prediction entirely - invalid line
                print(f"⚠️  Skipping {player.name} {stat_type}: invalid line (safe={bet_lines['safe_line']}, std={bet_lines['standard_line']}, long={bet_lines['long_shot_line']})")
                return None
            
            prediction.safe_line = bet_lines['safe_line']
            prediction.safe_probability = bet_lines['safe_probability']
            prediction.safe_under_probability = 1.0 - bet_lines['safe_probability']
            prediction.standard_line = bet_lines['standard_line']
            prediction.standard_probability = bet_lines['standard_probability']
            prediction.standard_under_probability = 1.0 - bet_lines['standard_probability']
            prediction.long_shot_line = bet_lines['long_shot_line']
            prediction.long_shot_probability = bet_lines['long_shot_probability']
            prediction.long_shot_under_probability = 1.0 - bet_lines['long_shot_probability']
            prediction.bet_type = bet_type
            prediction.pass_reason = pass_eval['reason'] if pass_eval['should_pass'] else None
            
            # New confidence fields
            prediction.line_source = bet_lines['line_source']
            confidence_data = pass_eval.get('confidence_data', {})
            prediction.confidence_level = confidence_data.get('tier', 'LOW')
            prediction.confidence_score = confidence_data.get('score', 0)
            
            # Store confidence reasons as JSON string
            import json
            prediction.confidence_reasons = json.dumps(confidence_data.get('reasons', []))
            
            prediction.data_as_of = game.game_date  # Use game date as data timestamp
            prediction.n_games_effective = bet_lines.get('effective_n', base_dist.get('sample_size', 0))
            
            # Apply lineup context confidence modifier if needed
            if lineup_context and lineup_context.get('confidence_modifier'):
                modifier = lineup_context['confidence_modifier']
                tier_order = ['MODEL_ONLY', 'LOW', 'MEDIUM', 'HIGH']
                current_idx = tier_order.index(prediction.confidence_level)
                if modifier < -0.1 and current_idx > 0:
                    prediction.confidence_level = tier_order[current_idx - 1]
                    prediction.confidence_score = max(0, prediction.confidence_score - 15)
            
            prediction.volatility_level = self.pass_rules.calculate_volatility_level(
                base_dist.get('cv'),
                stat_type=stat_type
            )
            prediction.reasoning = reasoning
            
            if is_new:
                self.db.add(prediction)
            
            predictions_created.append(prediction)
        
        # Return the primary prediction (safe > standard > long_shot) for backward compatibility
        primary_bet_type = 'safe' if 'safe' in qualifying_bet_types else \
                          'standard' if 'standard' in qualifying_bet_types else \
                          'long_shot' if 'long_shot' in qualifying_bet_types else 'pass'
        
        primary_prediction = next((p for p in predictions_created if p.bet_type == primary_bet_type), None)
        return primary_prediction if primary_prediction else (predictions_created[0] if predictions_created else None)
    
    def _build_reasoning(
        self,
        mean_adjustments: Dict,
        variance_adjustments: Dict,
        game_context: Dict,
        minutes_redist: Dict,
        pass_eval: Dict,
        blowout_info: Optional[Dict] = None,
        is_starter: bool = True,
        projected_minutes: float = 0.0,
        player_name: str = "",
        opponent_team_name: str = "",
        lineup_context: Optional[Dict] = None
    ) -> str:
        """Build human-readable reasoning for the prediction."""
        factors = []
        explanations = []
        
        # Player role context
        role_context = "Starter" if is_starter else "Bench player"
        
        # Blowout risk information - ENHANCED with better explanations
        if blowout_info and blowout_info.get('blowout_risk_high') and blowout_info.get('risk_score', 0) >= 0.6:
            risk_level = blowout_info.get('risk_level', 'HIGH')
            risk_score = blowout_info.get('risk_score', 0)
            point_spread = blowout_info.get('point_spread')
            
            if is_starter:
                explanations.append(f"⚠️ {role_context} in high blowout risk game ({risk_level}, {risk_score:.0%} risk)")
                if point_spread:
                    explanations.append(f"Team is {'heavily favored' if abs(point_spread) >= 10 else 'favored'} by {abs(point_spread):.1f} points")
                explanations.append("Starter may get pulled early if game becomes a blowout, reducing minutes and stats")
            else:
                explanations.append(f"✅ {role_context} in high blowout risk game ({risk_level}, {risk_score:.0%} risk)")
                if point_spread:
                    explanations.append(f"Team is {'heavily favored' if abs(point_spread) >= 10 else 'favored'} by {abs(point_spread):.1f} points")
                explanations.append("Bench player likely to get extended minutes in blowout scenario as starters rest")
                if projected_minutes > 0:
                    explanations.append(f"Projected {projected_minutes:.1f} minutes (increased due to blowout risk)")
            
            if blowout_info.get('risk_factors'):
                risk_factors = blowout_info['risk_factors'][:3]
                explanations.append(f"Risk factors: {', '.join(risk_factors)}")
        
        # Minutes adjustment explanation
        if mean_adjustments['minutes_factor'] != 1.0:
            minutes_change = (mean_adjustments['minutes_factor'] - 1.0) * 100
            if minutes_change > 0:
                explanations.append(f"📈 Projected {abs(minutes_change):.0f}% more minutes than usual")
            else:
                explanations.append(f"📉 Projected {abs(minutes_change):.0f}% fewer minutes than usual")
        
        # Defense matchup explanation
        if mean_adjustments['defense_factor'] != 1.0:
            defense_change = (mean_adjustments['defense_factor'] - 1.0) * 100
            if defense_change > 0:
                explanations.append(f"🎯 Favorable matchup: Opponent allows {abs(defense_change):.0f}% more than league average")
            else:
                explanations.append(f"🛡️ Tough matchup: Opponent allows {abs(defense_change):.0f}% less than league average")
        
        # Pace explanation
        if mean_adjustments['pace_factor'] != 1.0:
            pace_change = (mean_adjustments['pace_factor'] - 1.0) * 100
            if pace_change > 0:
                explanations.append(f"⚡ Fast-paced game: {abs(pace_change):.0f}% faster than league average (more opportunities)")
            else:
                explanations.append(f"🐌 Slow-paced game: {abs(pace_change):.0f}% slower than league average (fewer opportunities)")
        
        # Injury benefits
        if minutes_redist['benefits_from_injury']:
            minutes_increase = minutes_redist.get('minutes_increase', 0)
            usage_increase = minutes_redist.get('usage_increase_pct', 0)
            explanations.append(f"🏥 Teammate injury benefit: +{minutes_increase:.1f} min, +{usage_increase:.1f}% usage")
        
        # Injury stat boost
        if mean_adjustments.get('injury_stat_boost', 1.0) > 1.0:
            boost_pct = (mean_adjustments['injury_stat_boost'] - 1.0) * 100
            explanations.append(f"📊 Historical stat boost: Player averages +{boost_pct:.1f}% when teammates are injured")
        
        # Rest days
        rest_days = game_context.get('rest_days', -1)
        if rest_days == 0:
            explanations.append("🔄 Back-to-back game: May impact performance")
        elif rest_days >= 3:
            explanations.append(f"💤 Well-rested: {rest_days} days rest (positive factor)")
        
        # Matchup history
        if mean_adjustments.get('matchup_factor', 1.0) != 1.0:
            matchup_change = (mean_adjustments['matchup_factor'] - 1.0) * 100
            if matchup_change > 0:
                explanations.append(f"⭐ Strong history vs opponent: Player performs {abs(matchup_change):.0f}% better than average")
            else:
                explanations.append(f"📉 Weak history vs opponent: Player performs {abs(matchup_change):.0f}% worse than average")
        
        # Recent form
        if mean_adjustments.get('form_trend_factor', 1.0) != 1.0:
            form_change = (mean_adjustments['form_trend_factor'] - 1.0) * 100
            if form_change > 0:
                explanations.append(f"📈 Hot streak: Player performing {abs(form_change):.0f}% above season average recently")
            else:
                explanations.append(f"📉 Cold streak: Player performing {abs(form_change):.0f}% below season average recently")
        
        # Lineup context - NEW FEATURE
        if lineup_context and lineup_context.get('adjusted_performance'):
            impact_desc = lineup_context.get('lineup_impact', '')
            if impact_desc and 'missing' in impact_desc.lower():
                confidence_modifier = lineup_context.get('confidence_modifier', 0)
                if confidence_modifier < -0.1:
                    explanations.append(f"🏥 {impact_desc} (may inflate historical stats)")
                elif confidence_modifier < -0.05:
                    explanations.append(f"📊 {impact_desc} (slight adjustment needed)")
                else:
                    explanations.append(f"📈 {impact_desc}")

        # Home/Away
        if mean_adjustments.get('home_factor', 1.0) > 1.0:
            explanations.append("🏠 Home court advantage")
        elif mean_adjustments.get('home_factor', 1.0) < 1.0:
            explanations.append("✈️ Away game (slight disadvantage)")
        
        # Volatility warning
        if variance_adjustments['minutes_volatility'] > 1.1:
            explanations.append("⚠️ High minutes volatility: Playing time may vary significantly")
        
        # Combine explanations
        if explanations:
            return " | ".join(explanations)
        else:
            return "Baseline prediction based on historical performance"
    
    def generate_predictions_for_game(
        self,
        game_id: int,
        stat_types: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None
    ) -> Dict[str, int]:
        """
        Generate predictions for all players in a game.
        
        Returns:
            Dict with counts of predictions created/updated/skipped/errors
        """
        import logging
        from collections import defaultdict
        logger = logging.getLogger(__name__)

        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return {'created': 0, 'updated': 0}

        # Set default stat types if not provided
        if stat_types is None:
            stat_types = self.sport_config['stat_types']

        # Get players for both teams (filter by sport)
        home_players = self.db.query(Player).filter(
            Player.current_team_id == game.home_team_id,
            Player.sport == self.sport
        ).all()
        
        away_players = self.db.query(Player).filter(
            Player.current_team_id == game.away_team_id,
            Player.sport == self.sport
        ).all()
        
        all_players = home_players + away_players
        
        # PRE-FILTER: For upcoming games, filter out players who are Out/Doubtful/Questionable before processing
        # Also filter out players not in confirmed lineups
        # This saves time by not even trying to generate predictions for injured players or non-starters
        if game.game_status in ['scheduled', 'in_progress']:
            filtered_players = []
            for player in all_players:
                # Check injury status - skip if Out, Doubtful, or Questionable
                injury_status = self.injury_context.get_player_injury_status(player.player_id)
                if injury_status:
                    if injury_status['status'] in ['Out', 'Doubtful', 'Questionable']:
                        continue  # Skip injured/questionable players
                
                # ENHANCEMENT: Check if player is on the correct team
                # If current_team_id doesn't match game teams, try to find them in recent game stats
                if player.current_team_id not in [game.home_team_id, game.away_team_id]:
                    # Check if player has recent stats for either team in this game
                    from app.models.player_game_stat import PlayerGameStat
                    recent_stat = self.db.query(PlayerGameStat).join(Game).filter(
                        and_(
                            PlayerGameStat.player_id == player.player_id,
                            PlayerGameStat.team_id.in_([game.home_team_id, game.away_team_id]),
                            Game.game_date >= game.game_date - timedelta(days=30),
                            Game.game_status == 'finished',
                            PlayerGameStat.minutes_played > 0
                        )
                    ).order_by(desc(Game.game_date)).first()
                    
                    if recent_stat:
                        # Player has recent stats for one of the teams - update their team assignment
                        if player.current_team_id != recent_stat.team_id:
                            player.current_team_id = recent_stat.team_id
                            self.db.add(player)
                            logger.info(f"  Updated {player.name} team assignment: {recent_stat.team_id}")
                    else:
                        # No recent stats for either team - skip this player
                        continue  # Skip if not on either team
                
                # ENHANCEMENT: Check if lineup is confirmed - filter out players not in lineup
                team_id = game.home_team_id if player.current_team_id == game.home_team_id else game.away_team_id
                is_lineup_confirmed = self.lineup_service.is_lineup_confirmed(game_id, team_id)
                
                # If lineup is confirmed, only include players who are in the lineup
                if is_lineup_confirmed:
                    is_in_lineup = self.lineup_service.is_player_in_lineup(game_id, player.player_id)
                    if not is_in_lineup:
                        # Lineup is confirmed and player is not in it - skip this player
                        logger.debug(f"  Skipping {player.name} - not in confirmed lineup for game {game_id}")
                        continue
                
                filtered_players.append(player)
            all_players = filtered_players
        
        # ENHANCEMENT: Clean up predictions for players who are no longer on the correct team
        # This handles cases where team assignments were updated after predictions were generated
        existing_predictions = self.db.query(Prediction).filter(
            Prediction.game_id == game_id
        ).all()
        
        cleaned_up = 0
        for existing_pred in existing_predictions:
            player = self.db.query(Player).filter(Player.player_id == existing_pred.player_id).first()
            if player:
                # Check if player is still on a team in this game
                if player.current_team_id not in [game.home_team_id, game.away_team_id]:
                    # Player is not on either team - delete this prediction
                    self.db.delete(existing_pred)
                    cleaned_up += 1
        
        if cleaned_up > 0:
            self.db.commit()
            logger.info(f"  🧹 Cleaned up {cleaned_up} predictions for players not on correct team")
        
        created = 0
        updated = 0
        skipped = 0
        errors = defaultdict(int)  # Track error types
        
        total_predictions = len(all_players) * len(stat_types)
        processed = 0
        
        for player in all_players:
            for stat_type in stat_types:
                processed += 1
                # Log progress every 10 predictions or at completion
                if processed % 10 == 0 or processed == total_predictions:
                    progress_pct = int((processed / total_predictions) * 100) if total_predictions > 0 else 0
                    message = f"Processing: {processed}/{total_predictions} predictions ({progress_pct}%)"
                    print(f"  {message}", flush=True)
                    # Also log to logger if available
                    try:
                        import logging
                        import sys
                        logger = logging.getLogger(__name__)
                        logger.info(message)
                        sys.stdout.flush()  # Ensure output appears immediately
                    except:
                        pass
                    if progress_callback:
                        progress_callback({
                            'progress': progress_pct,
                            'processed': processed,
                            'total': total_predictions,
                            'message': message
                        })
                
                # Check if prediction already exists
                existing = self.db.query(Prediction).filter(
                    and_(
                        Prediction.player_id == player.player_id,
                        Prediction.game_id == game_id,
                        Prediction.stat_type == stat_type
                    )
                ).first()
                
                was_new = existing is None
                
                try:
                    prediction = self.generate_prediction(player.player_id, game_id, stat_type)
                    if prediction:
                        if was_new:
                            created += 1
                        else:
                            updated += 1
                    else:
                        skipped += 1
                    
                    # Commit every 20 predictions to avoid memory issues
                    if (created + updated) % 20 == 0:
                        self.db.commit()
                        
                except Exception as e:
                    error_type = type(e).__name__
                    errors[error_type] += 1
                    print(f"  ERROR ({error_type}): player {player.player_id}, stat {stat_type}: {e}")
                    skipped += 1
                    self.db.rollback()
                    continue
        
        # Generate and save combo bets for players with predictions
        combo_created, combo_updated = self._generate_combo_predictions_for_game(game_id, all_players)
        created += combo_created
        updated += combo_updated
        
        # Final commit
        self.db.commit()
        
        # Report error summary
        if errors:
            print(f"\n  ERROR SUMMARY:")
            for error_type, count in sorted(errors.items(), key=lambda x: -x[1]):
                print(f"    {error_type}: {count} occurrences")
        
        return {
            'created': created,
            'updated': updated,
            'skipped': skipped,
            'errors': dict(errors),
            'total_errors': sum(errors.values())
        }
    
    def _generate_combo_predictions_for_game(self, game_id: int, players: List) -> tuple[int, int]:
        """
        Generate and save combo bet predictions (points+rebounds, points+assists, rebounds+assists).
        
        Returns:
            Tuple of (created_count, updated_count)
        """
        created = 0
        updated = 0
        
        combo_types = [
            ("points_rebounds", "points", "rebounds"),
            ("points_assists", "points", "assists"),
            ("rebounds_assists", "rebounds", "assists")
        ]
        
        for player in players:
            for combo_type, stat1, stat2 in combo_types:
                # Get the individual predictions
                pred1 = self.db.query(Prediction).filter(
                    and_(
                        Prediction.game_id == game_id,
                        Prediction.player_id == player.player_id,
                        Prediction.stat_type == stat1,
                        Prediction.bet_type.in_(['safe', 'standard'])
                    )
                ).first()
                
                pred2 = self.db.query(Prediction).filter(
                    and_(
                        Prediction.game_id == game_id,
                        Prediction.player_id == player.player_id,
                        Prediction.stat_type == stat2,
                        Prediction.bet_type.in_(['safe', 'standard'])
                    )
                ).first()
                
                if not pred1 or not pred2:
                    continue  # Need both predictions to create combo
                
                # Check that both predictions have valid distribution parameters
                if (pred1.distribution_mean is None or pred1.distribution_std_dev is None or
                    pred2.distribution_mean is None or pred2.distribution_std_dev is None):
                    continue  # Skip if either prediction has None values
                
                # Combine distributions
                combined_mean = pred1.distribution_mean + pred2.distribution_mean
                combined_std = (pred1.distribution_std_dev ** 2 + pred2.distribution_std_dev ** 2) ** 0.5
                
                # Create combined distribution
                dist = norm(loc=combined_mean, scale=combined_std)
                
                # Calculate percentiles
                percentile_25 = float(dist.ppf(0.25))
                percentile_50 = float(dist.ppf(0.50))
                percentile_85 = float(dist.ppf(0.85))
                
                # Generate bet lines
                safe_line = combined_mean * 0.90
                safe_prob = float(1.0 - dist.cdf(safe_line))
                standard_line = combined_mean
                standard_prob = float(1.0 - dist.cdf(standard_line))
                long_shot_line = combined_mean * 1.15
                long_shot_prob = float(1.0 - dist.cdf(long_shot_line))
                
                # Check if prediction already exists
                existing = self.db.query(Prediction).filter(
                    and_(
                        Prediction.player_id == player.player_id,
                        Prediction.game_id == game_id,
                        Prediction.stat_type == combo_type
                    )
                ).first()
                
                if existing:
                    # Update existing
                    existing.distribution_mean = combined_mean
                    existing.distribution_std_dev = combined_std
                    existing.percentile_25 = percentile_25
                    existing.percentile_50 = percentile_50
                    existing.percentile_85 = percentile_85
                    existing.safe_line = safe_line
                    existing.safe_probability = safe_prob
                    existing.standard_line = standard_line
                    existing.standard_probability = standard_prob
                    existing.long_shot_line = long_shot_line
                    existing.long_shot_probability = long_shot_prob
                    
                    # Determine bet type
                    if safe_prob >= 0.70:
                        existing.bet_type = 'safe'
                    elif standard_prob >= 0.45:
                        existing.bet_type = 'standard'
                    elif 0.08 <= long_shot_prob <= 0.30:
                        existing.bet_type = 'long_shot'
                    else:
                        existing.bet_type = 'pass'
                    
                    existing.sample_size = min(pred1.sample_size or 0, pred2.sample_size or 0)
                    updated += 1
                else:
                    # Create new
                    prediction = Prediction(
                        player_id=player.player_id,
                        game_id=game_id,
                        stat_type=combo_type,
                        sport=self.sport,
                        distribution_mean=combined_mean,
                        distribution_std_dev=combined_std,
                        percentile_25=percentile_25,
                        percentile_50=percentile_50,
                        percentile_85=percentile_85,
                        safe_line=safe_line,
                        safe_probability=safe_prob,
                        standard_line=standard_line,
                        standard_probability=standard_prob,
                        long_shot_line=long_shot_line,
                        long_shot_probability=long_shot_prob,
                        sample_size=min(pred1.sample_size or 0, pred2.sample_size or 0),
                        bet_type='safe' if safe_prob >= 0.70 else ('standard' if standard_prob >= 0.45 else ('long_shot' if 0.08 <= long_shot_prob <= 0.30 else 'pass')),
                        confidence_level='HIGH' if combined_std / combined_mean < 0.3 else 'MEDIUM',
                        volatility_level='LOW' if combined_std / combined_mean < 0.25 else 'MEDIUM'
                    )
                    self.db.add(prediction)
                    created += 1
        
        return (created, updated)
    
    def generate_predictions_for_upcoming_games(
        self,
        days_ahead: int = 1,
        stat_types: List[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None
    ) -> Dict[str, int]:
        """
        Generate predictions for all upcoming games.
        
        Args:
            days_ahead: Number of days ahead to look for games
            stat_types: List of stat types to generate. If None, uses sport-specific defaults.
            progress_callback: Optional callback for progress updates
        
        Returns:
            Dict with summary statistics
        """
        # Use sport-specific default stat types if not provided
        if stat_types is None:
            stat_types = self.sport_config['stat_types']
        
        # Validate stat types for this sport
        for stat_type in stat_types:
            if stat_type not in self.sport_config['stat_types']:
                raise ValueError(f"Invalid stat type '{stat_type}' for sport '{self.sport}'. Valid types: {self.sport_config['stat_types']}")
        
        today = date.today()
        end_date = today + timedelta(days=days_ahead)
        
        games = self.db.query(Game).filter(
            and_(
                Game.sport == self.sport,
                Game.game_date >= today,
                Game.game_date <= end_date,
                Game.game_status.in_(['scheduled', 'in_progress'])
            )
        ).all()
        
        total_created = 0
        total_updated = 0
        total_skipped = 0
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Found {len(games)} upcoming games to process")
        
        for idx, game in enumerate(games):
            game_progress = int(((idx + 1) / len(games)) * 100) if len(games) > 0 else 0
            message = f"Processing game {idx+1}/{len(games)} (Game ID: {game.game_id})..."
            # Use both print and logger for visibility
            print(f"\n{message}", flush=True)
            import logging
            import sys
            logger = logging.getLogger(__name__)
            logger.info(message)
            sys.stdout.flush()  # Ensure output appears immediately
            if progress_callback:
                progress_callback({
                    'progress': game_progress,
                    'current_game': idx + 1,
                    'total_games': len(games),
                    'message': message
                })
            results = self.generate_predictions_for_game(game.game_id, stat_types, progress_callback)
            total_created += results['created']
            total_updated += results['updated']
            total_skipped += results.get('skipped', 0)
            result_msg = f"  Game {game.game_id}: Created {results['created']}, Updated {results['updated']}, Skipped {results.get('skipped', 0)}"
            print(result_msg)
            logger.info(result_msg)

        # Generate value ladders from the predictions we just created (focus on today's games)
        try:
            ladder_service = ValueLadderService()
            ladders_created = ladder_service.generate_ladders_from_predictions(
                self.db, self.sport, days_ahead
            )
            logger.info(f"✅ Generated {ladders_created} value ladders for today's games")
        except Exception as e:
            logger.error(f"⚠️ Failed to generate value ladders: {e}")

        return {
            'games_processed': len(games),
            'created': total_created,
            'updated': total_updated,
            'skipped': total_skipped,
            'ladders_created': ladders_created if 'ladders_created' in locals() else 0
        }
    
    def _get_league_averages(self, stat_type: str) -> tuple:
        """
        Get league average and std for a stat type from historical data.
        
        Returns:
            (league_mean, league_std) or (None, None) if not available
        """
        # Check cache first
        cache_key = f'{self.sport}_{stat_type}'
        if not hasattr(self, '_league_avg_cache'):
            self._league_avg_cache = {}
        
        if cache_key in self._league_avg_cache:
            return self._league_avg_cache[cache_key]
        
        try:
            from app.models.player_game_stat import PlayerGameStat
            from sqlalchemy import func
            
            # Map stat_type to ACTUAL database column (not nonexistent attributes)
            stat_column_map = {
                # NBA
                'points': PlayerGameStat.points,
                'rebounds': PlayerGameStat.rebounds,
                'assists': PlayerGameStat.assists,
                'three_pointers_made': PlayerGameStat.three_pointers_made,
                # NFL
                'passing_yards': PlayerGameStat.passing_yards,
                'rushing_yards': PlayerGameStat.rushing_yards,
                'receiving_yards': PlayerGameStat.receiving_yards,
                'receptions': PlayerGameStat.receptions,
                'passing_tds': PlayerGameStat.passing_tds,
                'rushing_tds': PlayerGameStat.rushing_tds,
                'receiving_tds': PlayerGameStat.receiving_tds,
                # MLB - use ACTUAL columns from model
                'hits': PlayerGameStat.hits,
                'home_runs': PlayerGameStat.home_runs,
                'total_bases': PlayerGameStat.total_bases,
                'strikeouts': PlayerGameStat.strikeouts,
                'rbis': PlayerGameStat.rbis,
                # Note: 'runs' column doesn't exist in PlayerGameStat model
            }
            
            stat_column = stat_column_map.get(stat_type)
            if stat_column is None:
                # No column exists for this stat type
                self._league_avg_cache[cache_key] = (None, None)
                return (None, None)
            
            # Query last 6 months of data for this sport
            from app.models.game import Game
            from datetime import date, timedelta
            
            cutoff_date = date.today() - timedelta(days=180)
            
            result = self.db.query(
                func.avg(stat_column).label('mean'),
                func.stddev(stat_column).label('std')
            ).join(Game).filter(
                Game.sport == self.sport,
                Game.game_status == 'finished',
                Game.game_date >= cutoff_date,
                stat_column.isnot(None),
                # Include ALL values including zeros (count stats can be 0)
                stat_column >= 0
            ).first()
            
            if result and result.mean is not None:
                league_mean = float(result.mean)
                league_std = float(result.std) if result.std else league_mean * 0.3
                self._league_avg_cache[cache_key] = (league_mean, league_std)
                return (league_mean, league_std)
            
        except Exception as e:
            print(f"Warning: Could not load league averages for {stat_type}: {e}")
        
        # Fallback defaults by sport and stat type
        fallback_averages = {
            'NBA': {
                'points': (20.0, 8.0),
                'rebounds': (6.0, 3.0),
                'assists': (4.0, 3.0),
                'three_pointers_made': (1.5, 1.5),
            },
            'NFL': {
                'passing_yards': (200.0, 80.0),
                'rushing_yards': (50.0, 30.0),
                'receiving_yards': (40.0, 25.0),
                'receptions': (4.0, 2.5),
                'passing_tds': (1.5, 1.0),
                'rushing_tds': (0.5, 0.5),
                'receiving_tds': (0.5, 0.5),
            },
            'MLB': {
                'hits': (0.81, 0.9),  # Per game including zeros
                'home_runs': (0.113, 0.33),  # Per game including zeros (~11% get >=1 HR)
                'total_bases': (1.33, 1.3),  # Per game including zeros
                'strikeouts': (0.8, 0.9),  # For batters
                'rbis': (0.5, 0.7),
            }
        }
        
        sport_defaults = fallback_averages.get(self.sport, {})
        result = sport_defaults.get(stat_type, (None, None))
        self._league_avg_cache[cache_key] = result
        return result
    
    def _get_days_since_last_game(self, player_id: int, current_game_date: date) -> Optional[int]:
        """
        Calculate days since player's last game.
        
        Returns:
            Number of days or None if no prior game found
        """
        from app.models.player_game_stat import PlayerGameStat
        from sqlalchemy import desc
        
        last_game_stat = self.db.query(PlayerGameStat).join(Game).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.game_date < current_game_date,
                Game.game_status == 'finished'
            )
        ).order_by(desc(Game.game_date)).first()
        
        if last_game_stat and last_game_stat.game:
            delta = current_game_date - last_game_stat.game.game_date
            return delta.days
        
        return None

