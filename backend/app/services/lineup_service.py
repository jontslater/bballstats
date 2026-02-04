"""
Lineup Service

Manages starting lineup confirmations and tracking.
"""
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Dict, Optional
from app.models.lineup import Lineup
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team


class LineupService:
    """Service for managing lineups."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def confirm_lineup(
        self,
        game_id: int,
        team_id: int,
        starter_player_ids: List[int],
        positions: Optional[List[str]] = None,
        bench_player_ids: Optional[List[int]] = None
    ) -> List[Lineup]:
        """
        Confirm a starting lineup for a game.
        
        Args:
            game_id: Game ID
            team_id: Team ID
            starter_player_ids: List of player IDs (starters, 3-5 players)
            positions: Optional list of positions (PG, SG, SF, PF, C)
                      If not provided, will use player's default position
            bench_player_ids: Optional list of bench player IDs
        
        Returns:
            List of Lineup objects created
        """
        if len(starter_player_ids) < 3:
            raise ValueError("Must provide at least 3 starters")
        
        # Remove existing lineup for this team in this game
        existing = self.db.query(Lineup).filter(
            and_(
                Lineup.game_id == game_id,
                Lineup.team_id == team_id
            )
        ).all()
        
        for lineup in existing:
            self.db.delete(lineup)
        
        # Create new lineup entries
        lineups = []
        
        # Add starters
        for idx, player_id in enumerate(starter_player_ids):
            player = self.db.query(Player).filter(Player.player_id == player_id).first()
            if not player:
                raise ValueError(f"Player {player_id} not found")
            
            position = positions[idx] if positions and idx < len(positions) else player.position
            
            lineup = Lineup(
                game_id=game_id,
                team_id=team_id,
                player_id=player_id,
                position=position,
                is_starter=True,
                confirmed_at=datetime.now()
            )
            
            self.db.add(lineup)
            lineups.append(lineup)
        
        # Add bench players if provided
        if bench_player_ids:
            for player_id in bench_player_ids:
                # Skip if already added as starter
                if player_id in starter_player_ids:
                    continue
                    
                player = self.db.query(Player).filter(Player.player_id == player_id).first()
                if not player:
                    continue  # Skip if player not found
                
                lineup = Lineup(
                    game_id=game_id,
                    team_id=team_id,
                    player_id=player_id,
                    position=player.position,
                    is_starter=False,
                    confirmed_at=datetime.now()
                )
                
                self.db.add(lineup)
                lineups.append(lineup)
        
        self.db.commit()
        
        for lineup in lineups:
            self.db.refresh(lineup)
        
        return lineups
    
    def get_game_lineups(self, game_id: int) -> Dict[int, List[Lineup]]:
        """
        Get lineups for a game, organized by team.
        
        Returns:
            Dict mapping team_id to list of Lineup objects
        """
        lineups = self.db.query(Lineup).filter(
            Lineup.game_id == game_id,
            Lineup.is_starter == True
        ).all()
        
        result = {}
        for lineup in lineups:
            if lineup.team_id not in result:
                result[lineup.team_id] = []
            result[lineup.team_id].append(lineup)
        
        return result
    
    def is_lineup_confirmed(self, game_id: int, team_id: int) -> bool:
        """
        Check if lineup is confirmed for a team in a game.
        
        Returns:
            True if lineup is confirmed (at least 3 starters), False otherwise
        """
        count = self.db.query(Lineup).filter(
            and_(
                Lineup.game_id == game_id,
                Lineup.team_id == team_id,
                Lineup.is_starter == True
            )
        ).count()
        
        # Consider lineup confirmed if we have at least 3 starters
        # (Some players may not be in database, but we have enough to confirm the lineup)
        return count >= 3
    
    def get_team_starters(self, game_id: int, team_id: int) -> List[Player]:
        """
        Get starting players for a team in a game.
        
        Returns:
            List of Player objects
        """
        lineups = self.db.query(Lineup).filter(
            and_(
                Lineup.game_id == game_id,
                Lineup.team_id == team_id,
                Lineup.is_starter == True
            )
        ).all()
        
        player_ids = [l.player_id for l in lineups]
        return self.db.query(Player).filter(Player.player_id.in_(player_ids)).all()
    
    def is_player_starter(self, game_id: int, player_id: int) -> bool:
        """
        Check if a player is confirmed as a starter for a specific game.
        
        Returns:
            True if player is confirmed starter, False otherwise
        """
        lineup = self.db.query(Lineup).filter(
            and_(
                Lineup.game_id == game_id,
                Lineup.player_id == player_id,
                Lineup.is_starter == True
            )
        ).first()
        return lineup is not None
    
    def is_player_in_lineup(self, game_id: int, player_id: int) -> bool:
        """
        Check if a player is in the lineup (starter or bench) for a specific game.
        
        Returns:
            True if player is in lineup (starter or bench), False otherwise
        """
        lineup = self.db.query(Lineup).filter(
            and_(
                Lineup.game_id == game_id,
                Lineup.player_id == player_id
            )
        ).first()
        
        return lineup is not None
    
    def get_players_in_lineup(self, game_id: int, team_id: int) -> List[int]:
        """
        Get all player IDs in the lineup (starters and bench) for a team in a game.
        
        Returns:
            List of player IDs
        """
        lineups = self.db.query(Lineup).filter(
            and_(
                Lineup.game_id == game_id,
                Lineup.team_id == team_id
            )
        ).all()
        
        return [l.player_id for l in lineups]
    
    def get_upcoming_games_without_lineups(self, days_ahead: int = 1) -> List[Game]:
        """
        Get upcoming games that don't have confirmed lineups.
        
        Args:
            days_ahead: Number of days ahead to check
        
        Returns:
            List of Game objects
        """
        from datetime import date, timedelta
        
        today = date.today()
        end_date = today + timedelta(days=days_ahead)
        
        # Get all upcoming games
        upcoming_games = self.db.query(Game).filter(
            and_(
                Game.game_date >= today,
                Game.game_date <= end_date,
                Game.game_status.in_(['scheduled', 'in_progress'])
            )
        ).all()
        
        # Filter to games without confirmed lineups
        games_without_lineups = []
        for game in upcoming_games:
            home_confirmed = self.is_lineup_confirmed(game.game_id, game.home_team_id)
            away_confirmed = self.is_lineup_confirmed(game.game_id, game.away_team_id)
            
            if not home_confirmed or not away_confirmed:
                games_without_lineups.append(game)
        
        return games_without_lineups
    
    def infer_lineup_from_game_stats(self, game_id: int) -> Dict[int, List[Lineup]]:
        """
        Infer starting lineup from game stats (for completed games).
        
        This looks at minutes played and assumes the 5 players with most minutes
        were starters (regardless of position).
        
        Returns:
            Dict mapping team_id to list of Lineup objects
        """
        from app.models.player_game_stat import PlayerGameStat
        
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return {}
        
        result = {}
        
        for team_id in [game.home_team_id, game.away_team_id]:
            # Get player stats for this team in this game, ordered by minutes (descending)
            stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game_id,
                    PlayerGameStat.team_id == team_id,
                    PlayerGameStat.minutes_played > 0
                )
            ).order_by(PlayerGameStat.minutes_played.desc()).all()
            
            if not stats:
                continue
            
            # Take top 5 players by minutes played as starters
            # (In NBA, starters typically play the most minutes)
            top_5_stats = stats[:5]
            
            # Create lineup entries
            lineups = []
            for stat in top_5_stats:
                player = self.db.query(Player).filter(Player.player_id == stat.player_id).first()
                if not player:
                    continue
                
                # Use player's position if available, otherwise use None
                position = player.position if player.position else None
                
                lineup = Lineup(
                    game_id=game_id,
                    team_id=team_id,
                    player_id=stat.player_id,
                    position=position,
                    is_starter=True,
                    confirmed_at=datetime.now()
                )
                lineups.append(lineup)
            
            # Only add if we found at least 3 starters (minimum for a valid lineup)
            if len(lineups) >= 3:
                result[team_id] = lineups
        
        return result

