"""
Redistribution Engine

Handles minutes and usage redistribution when players are injured.
"""
from sqlalchemy import and_, func
from sqlalchemy.orm import Session
from typing import Optional, Dict
from app.services.injury_impact_analyzer import InjuryImpactAnalyzer
from app.services.injury_context import InjuryContext
from app.models.player import Player


class RedistributionEngine:
    """Calculate minutes and usage redistribution due to injuries."""
    
    def __init__(self, db: Session):
        self.db = db
        self.impact_analyzer = InjuryImpactAnalyzer(db)
        self.injury_context = InjuryContext(db)
    
    def calculate_redistributed_minutes(
        self,
        player_id: int,
        team_id: int,
        base_minutes: float
    ) -> Dict[str, float]:
        """
        Calculate redistributed minutes for a player due to injuries.
        
        Returns:
            Dict with projected_minutes and minutes_increase
        """
        # Get team injury context
        context = self.injury_context.get_team_injury_context(team_id)
        
        # Check if this player benefits from injuries
        player_benefits = False
        minutes_increase = 0.0
        
        for impact_data in context.get('expected_impacts', []):
            if impact_data.get('player_id') == player_id:
                # This player benefits from injuries
                player_benefits = True
                # Get average minutes increase from all impacts
                impacts = impact_data.get('impacts', [])
                if impacts:
                    avg_increase = sum(i.get('minutes_increase', 0) for i in impacts) / len(impacts)
                    minutes_increase = max(minutes_increase, avg_increase)
        
        # If no historical data, use intelligent estimates based on injured player
        if player_benefits and minutes_increase == 0:
            # Get injured players' average minutes to estimate redistribution
            injured_players = context.get('active_injuries', [])
            if injured_players:
                # Get average minutes of injured players at same/similar position
                from app.models.player_game_stat import PlayerGameStat
                from app.models.game import Game
                
                total_injured_minutes = 0
                injured_count = 0
                player_position = None
                
                # Get player's position
                player = self.db.query(Player).filter(Player.player_id == player_id).first()
                if player:
                    player_position = player.position
                
                for injury in injured_players:
                    injured_player_id = injury.get('player_id')
                    if injured_player_id:
                        injured_player = self.db.query(Player).filter(Player.player_id == injured_player_id).first()
                        if injured_player:
                            # Check if same position
                            position_match = (injured_player.position == player_position) if player_position else False
                            
                            # Get injured player's average minutes
                            avg_min = self.db.query(func.avg(PlayerGameStat.minutes_played)).join(
                                Game, PlayerGameStat.game_id == Game.game_id
                            ).filter(
                                PlayerGameStat.player_id == injured_player_id,
                                Game.game_status == 'finished',
                                PlayerGameStat.minutes_played > 0
                            ).scalar()
                            
                            if avg_min:
                                total_injured_minutes += avg_min
                                injured_count += 1
                                
                                # If same position, player gets more minutes
                                if position_match:
                                    minutes_increase = max(minutes_increase, min(avg_min * 0.6, 12.0))
                                else:
                                    minutes_increase = max(minutes_increase, min(avg_min * 0.3, 8.0))
                
                # If we couldn't calculate from injured players, use default
                if minutes_increase == 0:
                    minutes_increase = 7.5
            else:
                # No injured players but player benefits? Use conservative default
                minutes_increase = 5.0
        
        # Ensure minutes_increase is not None before addition
        if minutes_increase is None:
            minutes_increase = 0.0
        
        projected_minutes = base_minutes + minutes_increase
        
        return {
            'base_minutes': base_minutes,
            'minutes_increase': round(minutes_increase, 1),
            'projected_minutes': round(projected_minutes, 1),
            'benefits_from_injury': player_benefits
        }
    
    def calculate_redistributed_usage(
        self,
        player_id: int,
        team_id: int,
        base_usage: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculate redistributed usage rate for a player due to injuries.
        
        Args:
            player_id: Player ID
            team_id: Team ID
            base_usage: Base usage rate (if None, will calculate from historical data)
        
        Returns:
            Dict with projected_usage and usage_increase
        """
        # Get base usage if not provided
        if base_usage is None:
            from app.services.distribution_engine import DistributionEngine
            dist_engine = DistributionEngine(self.db)
            base_usage = dist_engine.get_historical_usage_rate(player_id) or 0.20  # Default 20%
        
        # Ensure base_usage is not None (safety check)
        if base_usage is None:
            base_usage = 0.20
        
        # Get team injury context
        context = self.injury_context.get_team_injury_context(team_id)
        
        # Check if this player benefits from injuries
        player_benefits = False
        usage_increase = 0.0
        
        for impact_data in context.get('expected_impacts', []):
            if impact_data.get('player_id') == player_id:
                player_benefits = True
                # Calculate usage increase from historical impacts
                impacts = impact_data.get('impacts', [])
                if impacts:
                    # Estimate usage increase based on points increase
                    # Points increase correlates with usage increase
                    avg_points_increase = sum(i.get('points_increase', 0) for i in impacts) / len(impacts)
                    # Rough conversion: 1 point increase ≈ 0.01 usage increase
                    usage_increase = max(usage_increase, avg_points_increase * 0.01)
        
        # If no historical data but player benefits, use conservative estimate
        if player_benefits and usage_increase == 0:
            # Conservative: 10-15% usage increase for primary backup
            usage_increase = base_usage * 0.12
        
        # Ensure usage_increase is not None before addition
        if usage_increase is None:
            usage_increase = 0.0
        
        projected_usage = base_usage + usage_increase
        # Cap usage at reasonable maximum (40%)
        projected_usage = min(projected_usage, 0.40)
        
        return {
            'base_usage': round(base_usage, 3),
            'usage_increase': round(usage_increase, 3),
            'projected_usage': round(projected_usage, 3),
            'usage_change_pct': round((usage_increase / base_usage * 100) if base_usage > 0 else 0, 1),
            'benefits_from_injury': player_benefits
        }
    
    def is_minutes_locked(
        self,
        player_id: int,
        team_id: int
    ) -> bool:
        """
        Determine if player's minutes are locked (stable starter).
        
        Returns:
            True if minutes are locked, False otherwise
        """
        from datetime import date, timedelta
        from app.models.lineup import Lineup
        from app.models.game import Game
        from app.models.player_game_stat import PlayerGameStat
        
        # Check if player has been a consistent starter recently
        thirty_days_ago = date.today() - timedelta(days=30)
        
        # Count games where player was a starter
        recent_starter_games = self.db.query(Lineup).join(Game).filter(
            and_(
                Lineup.player_id == player_id,
                Lineup.is_starter == True,
                Game.game_date >= thirty_days_ago,
                Game.game_status == 'finished'
            )
        ).count()
        
        # Count total recent games
        recent_total_games = self.db.query(PlayerGameStat).join(Game).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.game_date >= thirty_days_ago,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).count()
        
        if recent_total_games == 0:
            return False
        
        # Calculate starter rate
        starter_rate = recent_starter_games / recent_total_games
        
        # Get average minutes
        avg_minutes = self.db.query(func.avg(PlayerGameStat.minutes_played)).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.game_date >= thirty_days_ago,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).scalar()
        
        # Minutes are locked if:
        # 1. Started in 80%+ of recent games AND
        # 2. Average minutes >= 25 (significant role)
        return starter_rate >= 0.80 and (avg_minutes or 0) >= 25
    
    def is_usage_stable(
        self,
        player_id: int,
        team_id: int
    ) -> bool:
        """
        Determine if player's usage is stable.
        
        Returns:
            True if usage is stable, False otherwise
        """
        # Check if player's usage depends on others being injured
        context = self.injury_context.get_team_injury_context(team_id)
        
        for impact_data in context.get('expected_impacts', []):
            if impact_data.get('player_id') == player_id:
                # Player benefits from injuries, so usage is not stable
                return False
        
        return True

