"""
Player Matchup Service

Analyzes individual player vs player defensive matchups.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import Dict, List, Optional
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team


class PlayerMatchupService:
    """Analyze individual player vs player matchups."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def find_defensive_matchup(
        self,
        offensive_player_id: int,
        opponent_team_id: int,
        position: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Find the most likely defensive matchup for a player.
        
        Uses position and recent lineup data to identify primary defender.
        
        Returns:
            Dict with matchup information
        """
        offensive_player = self.db.query(Player).filter(Player.player_id == offensive_player_id).first()
        if not offensive_player:
            return None
        
        # Get opponent team's players at the same position (likely defender)
        opponent_players = self.db.query(Player).filter(
            and_(
                Player.current_team_id == opponent_team_id,
                Player.position == (position or offensive_player.position)
            )
        ).all()
        
        if not opponent_players:
            return None
        
        # For now, return the primary defender (first player found)
        # In a full implementation, would analyze lineup data to find actual matchup
        primary_defender = opponent_players[0]
        
        return {
            'offensive_player_id': offensive_player_id,
            'offensive_player_name': offensive_player.name,
            'defender_id': primary_defender.player_id,
            'defender_name': primary_defender.name,
            'position': offensive_player.position,
            'confidence': 'LOW'  # Would be higher with actual lineup data
        }
    
    def analyze_player_vs_player_history(
        self,
        offensive_player_id: int,
        defender_player_id: int,
        season_id: Optional[int] = None
    ) -> Dict:
        """
        Analyze historical performance when these two players matched up.
        
        Returns:
            Dict with matchup statistics
        """
        from app.models.season import Season
        
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return {'error': 'No season found'}
            season_id = season.season_id
        
        # Find games where both players played
        # This is simplified - would need actual defensive assignment data
        offensive_games = self.db.query(Game).join(
            PlayerGameStat, Game.game_id == PlayerGameStat.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == offensive_player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        ).all()
        
        defender_games = self.db.query(Game).join(
            PlayerGameStat, Game.game_id == PlayerGameStat.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == defender_player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        ).all()
        
        # Find games where they played against each other
        offensive_game_ids = {g.game_id for g in offensive_games}
        defender_game_ids = {g.game_id for g in defender_games}
        matchup_game_ids = offensive_game_ids.intersection(defender_game_ids)
        
        if len(matchup_game_ids) < 3:
            return {
                'games_played': len(matchup_game_ids),
                'insufficient_data': True
            }
        
        # Get offensive player's stats in these games
        matchup_stats = self.db.query(PlayerGameStat).filter(
            and_(
                PlayerGameStat.player_id == offensive_player_id,
                PlayerGameStat.game_id.in_(list(matchup_game_ids))
            )
        ).all()
        
        if not matchup_stats:
            return {'error': 'No stats found'}
        
        # Calculate averages
        avg_points = sum(s.points or 0 for s in matchup_stats) / len(matchup_stats)
        avg_rebounds = sum(s.rebounds or 0 for s in matchup_stats) / len(matchup_stats)
        avg_assists = sum(s.assists or 0 for s in matchup_stats) / len(matchup_stats)
        avg_minutes = sum(s.minutes_played or 0 for s in matchup_stats) / len(matchup_stats)
        
        # Compare to season average
        all_season_stats = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == offensive_player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).all()
        
        if len(all_season_stats) >= 10:
            season_avg_points = sum(s.points or 0 for s in all_season_stats) / len(all_season_stats)
            season_avg_rebounds = sum(s.rebounds or 0 for s in all_season_stats) / len(all_season_stats)
            season_avg_assists = sum(s.assists or 0 for s in all_season_stats) / len(all_season_stats)
            
            # Calculate matchup factor
            points_factor = avg_points / season_avg_points if season_avg_points > 0 else 1.0
            rebounds_factor = avg_rebounds / season_avg_rebounds if season_avg_rebounds > 0 else 1.0
            assists_factor = avg_assists / season_avg_assists if season_avg_assists > 0 else 1.0
        else:
            points_factor = rebounds_factor = assists_factor = 1.0
            season_avg_points = season_avg_rebounds = season_avg_assists = None
        
        return {
            'games_played': len(matchup_stats),
            'avg_points': round(avg_points, 2),
            'avg_rebounds': round(avg_rebounds, 2),
            'avg_assists': round(avg_assists, 2),
            'avg_minutes': round(avg_minutes, 2),
            'season_avg_points': round(season_avg_points, 2) if season_avg_points else None,
            'points_factor': round(points_factor, 3),
            'rebounds_factor': round(rebounds_factor, 3),
            'assists_factor': round(assists_factor, 3),
            'matchup_advantage': 'POSITIVE' if points_factor > 1.05 else 'NEGATIVE' if points_factor < 0.95 else 'NEUTRAL'
        }
    
    def get_matchup_adjustment(
        self,
        offensive_player_id: int,
        opponent_team_id: int,
        stat_type: str,
        season_id: Optional[int] = None
    ) -> float:
        """
        Get matchup adjustment factor for a player vs team.
        
        Returns:
            Adjustment factor (0.90 to 1.10)
        """
        matchup_info = self.find_defensive_matchup(offensive_player_id, opponent_team_id)
        
        if not matchup_info or matchup_info.get('confidence') == 'LOW':
            return 1.0  # No adjustment if uncertain
        
        defender_id = matchup_info.get('defender_id')
        if not defender_id:
            return 1.0
        
        history = self.analyze_player_vs_player_history(
            offensive_player_id, defender_id, season_id
        )
        
        if history.get('insufficient_data') or history.get('games_played', 0) < 3:
            return 1.0
        
        # Use appropriate factor based on stat type
        if stat_type == 'points':
            factor = history.get('points_factor', 1.0)
        elif stat_type == 'rebounds':
            factor = history.get('rebounds_factor', 1.0)
        elif stat_type == 'assists':
            factor = history.get('assists_factor', 1.0)
        else:
            factor = 1.0
        
        # Clamp to reasonable range
        factor = max(0.90, min(1.10, factor))
        
        return round(factor, 3)

