"""
Pace Calculator

Calculates team and game pace (possessions per game).
"""
from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import Session
from typing import Optional, Dict
from app.models.game import Game
from app.models.player_game_stat import PlayerGameStat
from app.models.team import Team
from app.models.season import Season


class PaceCalculator:
    """Calculate team and game pace."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_team_pace(
        self,
        team_id: int,
        season_id: Optional[int] = None
    ) -> Optional[float]:
        """
        Calculate average pace for a team.
        
        Pace = (FGA + 0.44 * FTA + TO) / 2
        This is a simplified formula - actual NBA pace uses play-by-play data.
        
        Args:
            team_id: Team to analyze
            season_id: Season to analyze (default: current)
        
        Returns:
            Average pace (possessions per game) or None if insufficient data
        """
        # Get season if not provided
        if season_id is None:
            season = self.db.query(Season).filter(
                Season.is_current == True
            ).first()
            if not season:
                raise ValueError("No current season found.")
            season_id = season.season_id
        
        # Get all games for this team
        team_games = self.db.query(Game).filter(
            and_(
                or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        ).all()
        
        if not team_games:
            return None
        
        total_pace = 0
        games_counted = 0
        
        for game in team_games:
            # Get team stats for this game
            team_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.team_id == team_id
                )
            ).all()
            
            if not team_stats:
                continue
            
            # Calculate possessions for this game
            total_fga = sum(s.field_goals_attempted or 0 for s in team_stats)
            total_fta = sum(s.free_throws_attempted or 0 for s in team_stats)
            total_to = sum(s.turnovers or 0 for s in team_stats)
            
            # Simplified pace formula
            possessions = (total_fga + 0.44 * total_fta + total_to) / 2
            
            total_pace += possessions
            games_counted += 1
        
        if games_counted == 0:
            return None
        
        return round(total_pace / games_counted, 2)
    
    def calculate_recent_team_pace(
        self,
        team_id: int,
        season_id: Optional[int] = None,
        last_n_games: int = 10
    ) -> Optional[float]:
        """
        Calculate team's pace in recent games (last N games).
        
        Returns:
            Average pace in last N games, or None if insufficient data
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return None
            season_id = season.season_id
        
        # Get team's last N finished games
        from sqlalchemy import desc
        
        recent_games = self.db.query(Game).filter(
            and_(
                or_(
                    Game.home_team_id == team_id,
                    Game.away_team_id == team_id
                ),
                Game.season_id == season_id,
                Game.game_status == 'finished',
                Game.game_date.isnot(None)
            )
        ).order_by(desc(Game.game_date)).limit(last_n_games).all()
        
        if len(recent_games) < 5:  # Need at least 5 games
            return None
        
        # Calculate pace for each game
        paces = []
        for game in recent_games:
            game_pace = self.calculate_game_pace(game.game_id)
            if game_pace:
                paces.append(game_pace)
        
        if len(paces) < 3:  # Need at least 3 games with pace data
            return None
        
        avg_pace = sum(paces) / len(paces)
        return round(avg_pace, 2)
    
    def calculate_game_pace(self, game_id: int) -> Optional[float]:
        """
        Calculate pace for a specific game.
        
        Returns:
            Game pace (possessions) or None
        """
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game or game.game_status != 'finished':
            return None
        
        # Get stats for both teams
        home_stats = self.db.query(PlayerGameStat).filter(
            and_(
                PlayerGameStat.game_id == game_id,
                PlayerGameStat.team_id == game.home_team_id
            )
        ).all()
        
        away_stats = self.db.query(PlayerGameStat).filter(
            and_(
                PlayerGameStat.game_id == game_id,
                PlayerGameStat.team_id == game.away_team_id
            )
        ).all()
        
        if not home_stats or not away_stats:
            return None
        
        # Calculate possessions for both teams
        home_fga = sum(s.field_goals_attempted or 0 for s in home_stats)
        home_fta = sum(s.free_throws_attempted or 0 for s in home_stats)
        home_to = sum(s.turnovers or 0 for s in home_stats)
        home_possessions = (home_fga + 0.44 * home_fta + home_to) / 2
        
        away_fga = sum(s.field_goals_attempted or 0 for s in away_stats)
        away_fta = sum(s.free_throws_attempted or 0 for s in away_stats)
        away_to = sum(s.turnovers or 0 for s in away_stats)
        away_possessions = (away_fga + 0.44 * away_fta + away_to) / 2
        
        # Average of both teams
        game_pace = (home_possessions + away_possessions) / 2
        
        return round(game_pace, 2)
    
    def calculate_all_team_paces(self, season_id: Optional[int] = None) -> Dict[int, float]:
        """
        Calculate pace for all teams.
        
        Returns:
            Dict mapping team_id to pace
        """
        teams = self.db.query(Team).all()
        paces = {}
        
        for team in teams:
            pace = self.calculate_team_pace(team.team_id, season_id)
            if pace:
                paces[team.team_id] = pace
        
        return paces

