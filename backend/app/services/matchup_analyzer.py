"""
Player-Team Matchup Analyzer

Analyzes historical performance of players against specific teams.
"""
from sqlalchemy import and_, func
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.player_team_matchup import PlayerTeamMatchup
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.season import Season


class MatchupAnalyzer:
    """Analyze player performance against specific teams."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_all_matchups(self, season_id: Optional[int] = None) -> dict:
        """
        Calculate matchups for all players vs all teams.
        
        Returns:
            Dict with counts of records created/updated
        """
        # Get season if not provided
        if season_id is None:
            season = self.db.query(Season).filter(
                Season.is_current == True
            ).first()
            if not season:
                raise ValueError("No current season found. Please specify season_id.")
            season_id = season.season_id
        
        # Get all unique player-team combinations from game stats
        matchups_query = self.db.query(
            PlayerGameStat.player_id,
            PlayerGameStat.opponent_team_id
        ).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.opponent_team_id.isnot(None)
            )
        ).distinct().all()
        
        created = 0
        updated = 0
        
        for player_id, opponent_team_id in matchups_query:
            result = self.calculate_player_team_matchup(
                player_id=player_id,
                opponent_team_id=opponent_team_id,
                season_id=season_id
            )
            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1
        
        return {"created": created, "updated": updated}
    
    def calculate_player_team_matchup(
        self,
        player_id: int,
        opponent_team_id: int,
        season_id: int,
        min_games: int = 1
    ) -> Optional[str]:
        """
        Calculate matchup stats for a player against a specific team.
        
        Args:
            player_id: Player to analyze
            opponent_team_id: Team the player faced
            season_id: Season to analyze
            min_games: Minimum games required
        
        Returns:
            "created", "updated", or None if insufficient data
        """
        # Get all games where this player faced this team
        matchup_stats = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                PlayerGameStat.opponent_team_id == opponent_team_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).order_by(Game.game_date.desc()).all()
        
        if len(matchup_stats) < min_games:
            return None
        
        # Calculate averages
        total_games = len(matchup_stats)
        avg_points = sum(s.points or 0 for s in matchup_stats) / total_games
        avg_rebounds = sum(s.rebounds or 0 for s in matchup_stats) / total_games
        avg_assists = sum(s.assists or 0 for s in matchup_stats) / total_games
        avg_minutes = sum(s.minutes_played or 0 for s in matchup_stats) / total_games
        
        # Calculate last 5 games average
        last_5_stats = matchup_stats[:5] if len(matchup_stats) >= 5 else matchup_stats
        last_5_avg_points = sum(s.points or 0 for s in last_5_stats) / len(last_5_stats) if last_5_stats else None
        
        # Note: PlayerTeamMatchup model doesn't have home/away splits
        # We can add them later if needed
        
        # Get or create matchup record
        matchup = self.db.query(PlayerTeamMatchup).filter(
            and_(
                PlayerTeamMatchup.player_id == player_id,
                PlayerTeamMatchup.opponent_team_id == opponent_team_id,
                PlayerTeamMatchup.season_id == season_id
            )
        ).first()
        
        is_new = matchup is None
        if is_new:
            matchup = PlayerTeamMatchup(
                player_id=player_id,
                opponent_team_id=opponent_team_id,
                season_id=season_id
            )
        
        # Update stats
        matchup.games_played = total_games
        matchup.avg_points = round(avg_points, 2)
        matchup.avg_rebounds = round(avg_rebounds, 2)
        matchup.avg_assists = round(avg_assists, 2)
        matchup.avg_minutes = round(avg_minutes, 2)
        matchup.last_5_games_avg_points = round(last_5_avg_points, 2) if last_5_avg_points else None
        
        # Calculate best/worst games
        all_points = [s.points for s in matchup_stats]
        matchup.best_game_points = max(all_points) if all_points else None
        matchup.worst_game_points = min(all_points) if all_points else None
        
        if is_new:
            self.db.add(matchup)
        
        self.db.commit()
        self.db.refresh(matchup)
        
        return "created" if is_new else "updated"

