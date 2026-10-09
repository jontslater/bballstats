"""
League Averages Calculator

Calculates league-wide averages for use in prediction adjustments.
"""
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from typing import Dict, Optional
from app.models.team_position_defense import TeamPositionDefense
from app.services.pace_calculator import PaceCalculator
from app.models.game import Game
from app.models.player_game_stat import PlayerGameStat
from app.models.season import Season


class LeagueAverages:
    """Calculate league-wide averages."""
    
    def __init__(self, db: Session, pace_calculator: Optional[PaceCalculator] = None):
        self.db = db
        self._pace_calc = pace_calculator or PaceCalculator(db)
        self._league_pace_cache: Dict[int, float] = {}
    
    def calculate_league_avg_pace(self, season_id: Optional[int] = None) -> float:
        """
        Calculate league average pace (possessions per game).
        
        Returns:
            Average pace across all teams
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return 100.0  # Default fallback
            season_id = season.season_id

        if season_id in self._league_pace_cache:
            return self._league_pace_cache[season_id]
        
        all_paces = self._pace_calc.calculate_all_team_paces(season_id)
        
        if not all_paces:
            self._league_pace_cache[season_id] = 100.0
            return 100.0  # Default fallback
        
        avg_pace = round(sum(all_paces.values()) / len(all_paces), 2)
        self._league_pace_cache[season_id] = avg_pace
        return avg_pace
    
    def calculate_league_avg_points_by_position(
        self,
        position: str,
        season_id: Optional[int] = None
    ) -> float:
        """
        Calculate league average points allowed to a position.
        
        Args:
            position: Position (PG, SG, SF, PF, C)
            season_id: Season ID
        
        Returns:
            Average points allowed to this position across all teams
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return 20.0  # Default fallback
            season_id = season.season_id
        
        # Get all team position defense stats
        defenses = self.db.query(TeamPositionDefense).filter(
            and_(
                TeamPositionDefense.position == position,
                TeamPositionDefense.season_id == season_id,
                TeamPositionDefense.avg_points_allowed.isnot(None)
            )
        ).all()
        
        if not defenses:
            # Fallback: calculate from player stats
            return self._calculate_from_player_stats(position, season_id)
        
        avg_points = sum(d.avg_points_allowed for d in defenses) / len(defenses)
        return round(avg_points, 2)
    
    def _calculate_from_player_stats(
        self,
        position: str,
        season_id: int
    ) -> float:
        """Calculate league average from player stats as fallback."""
        from app.models.player import Player
        
        # Get all players at this position
        players = self.db.query(Player).filter(Player.position == position).all()
        
        if not players:
            return 20.0  # Default
        
        player_ids = [p.player_id for p in players]
        
        # Get average points for these players
        avg_points = self.db.query(
            func.avg(PlayerGameStat.points)
        ).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id.in_(player_ids),
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).scalar()
        
        return round(avg_points or 20.0, 2)
    
    def calculate_league_avg_rebounds_by_position(
        self,
        position: str,
        season_id: Optional[int] = None
    ) -> float:
        """
        Calculate league average rebounds allowed to a position.
        
        Args:
            position: Position (PG, SG, SF, PF, C)
            season_id: Season ID
        
        Returns:
            Average rebounds allowed to this position across all teams
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return 5.0  # Default fallback
            season_id = season.season_id
        
        # Get all team position defense stats
        defenses = self.db.query(TeamPositionDefense).filter(
            and_(
                TeamPositionDefense.position == position,
                TeamPositionDefense.season_id == season_id,
                TeamPositionDefense.avg_rebounds_allowed.isnot(None)
            )
        ).all()
        
        if not defenses:
            # Fallback: calculate from player stats
            return self._calculate_rebounds_from_player_stats(position, season_id)
        
        avg_rebounds = sum(d.avg_rebounds_allowed for d in defenses) / len(defenses)
        return round(avg_rebounds, 2)
    
    def calculate_league_avg_assists_by_position(
        self,
        position: str,
        season_id: Optional[int] = None
    ) -> float:
        """
        Calculate league average assists allowed to a position.
        
        Args:
            position: Position (PG, SG, SF, PF, C)
            season_id: Season ID
        
        Returns:
            Average assists allowed to this position across all teams
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return 4.0  # Default fallback
            season_id = season.season_id
        
        # Get all team position defense stats
        defenses = self.db.query(TeamPositionDefense).filter(
            and_(
                TeamPositionDefense.position == position,
                TeamPositionDefense.season_id == season_id,
                TeamPositionDefense.avg_assists_allowed.isnot(None)
            )
        ).all()
        
        if not defenses:
            # Fallback: calculate from player stats
            return self._calculate_assists_from_player_stats(position, season_id)
        
        avg_assists = sum(d.avg_assists_allowed for d in defenses) / len(defenses)
        return round(avg_assists, 2)
    
    def _calculate_rebounds_from_player_stats(
        self,
        position: str,
        season_id: int
    ) -> float:
        """Calculate league average rebounds from player stats as fallback."""
        from app.models.player import Player
        
        players = self.db.query(Player).filter(Player.position == position).all()
        
        if not players:
            return 5.0  # Default
        
        player_ids = [p.player_id for p in players]
        
        avg_rebounds = self.db.query(
            func.avg(PlayerGameStat.rebounds)
        ).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id.in_(player_ids),
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).scalar()
        
        return round(avg_rebounds or 5.0, 2)
    
    def _calculate_assists_from_player_stats(
        self,
        position: str,
        season_id: int
    ) -> float:
        """Calculate league average assists from player stats as fallback."""
        from app.models.player import Player
        
        players = self.db.query(Player).filter(Player.position == position).all()
        
        if not players:
            return 4.0  # Default
        
        player_ids = [p.player_id for p in players]
        
        avg_assists = self.db.query(
            func.avg(PlayerGameStat.assists)
        ).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id.in_(player_ids),
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).scalar()
        
        return round(avg_assists or 4.0, 2)
    
    def get_all_league_averages(self, season_id: Optional[int] = None) -> Dict:
        """
        Get all league averages.
        
        Returns:
            Dict with all league averages
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if season:
                season_id = season.season_id
        
        return {
            'pace': self.calculate_league_avg_pace(season_id),
            'points_by_position': {
                'PG': self.calculate_league_avg_points_by_position('PG', season_id),
                'SG': self.calculate_league_avg_points_by_position('SG', season_id),
                'SF': self.calculate_league_avg_points_by_position('SF', season_id),
                'PF': self.calculate_league_avg_points_by_position('PF', season_id),
                'C': self.calculate_league_avg_points_by_position('C', season_id),
            }
        }

