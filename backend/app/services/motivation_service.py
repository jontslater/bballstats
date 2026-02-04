"""
Motivation Service

Analyzes psychological and motivational factors that affect player performance.
Includes playoff pressure, rivalries, revenge games, and contract situations.
"""

from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Tuple
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.player import Player
import statistics


class MotivationService:
    """Analyze motivational factors affecting player performance."""

    def __init__(self, db: Session):
        self.db = db

    def calculate_motivation_multiplier(
        self,
        player_id: int,
        game_id: int,
        season_id: Optional[int] = None
    ) -> float:
        """
        Calculate motivation multiplier based on game context.

        Args:
            player_id: Player to analyze
            game_id: Game to analyze
            season_id: Season for context

        Returns:
            Motivation multiplier (0.95 to 1.10)
        """
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return 1.0

        multiplier = 1.0

        # Playoff motivation (simplified - would need playoff schedule data)
        playoff_boost = self._calculate_playoff_motivation(game)
        multiplier *= playoff_boost

        # Rivalry motivation
        rivalry_boost = self._calculate_rivalry_motivation(player_id, game)
        multiplier *= rivalry_boost

        # Revenge motivation (after embarrassing loss)
        revenge_boost = self._calculate_revenge_motivation(player_id, game)
        multiplier *= revenge_boost

        # Streak motivation (breaking losing streak, extending winning streak)
        streak_boost = self._calculate_streak_motivation(player_id, game)
        multiplier *= streak_boost

        return max(0.95, min(1.10, multiplier))  # Clamp to reasonable range

    def _calculate_playoff_motivation(self, game: Game) -> float:
        """Calculate playoff motivation boost."""
        # Simplified: assume higher motivation in potential playoff games
        # In a real implementation, would check playoff standings and implications
        return 1.03  # 3% boost for playoff implications

    def _calculate_rivalry_motivation(self, player_id: int, game: Game) -> float:
        """Calculate rivalry game motivation boost."""
        # Check if this is a notable rivalry matchup
        # Simplified: assume some games have rivalry context
        rivalry_teams = {
            # Example rivalries - would be configurable
            ('LAL', 'BOS'): True,  # Lakers vs Celtics
            ('GSW', 'LAL'): True,  # Warriors vs Lakers
        }

        # Get team abbreviations (simplified)
        rivalry_key = ('TEAM1', 'TEAM2')  # Would need actual team mapping

        if rivalry_key in rivalry_teams:
            return 1.04  # 4% boost for rivalry games

        return 1.0

    def _calculate_revenge_motivation(self, player_id: int, game: Game) -> float:
        """Calculate revenge motivation after embarrassing loss."""
        # Check recent performance against this opponent
        recent_games_vs_opponent = self.db.query(PlayerGameStat, Game).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                or_(Game.home_team_id == game.away_team_id, Game.away_team_id == game.away_team_id),
                Game.game_date < game.game_date,
                Game.game_status == 'finished'
            )
        ).order_by(desc(Game.game_date)).limit(3).all()

        if recent_games_vs_opponent:
            # Check for embarrassing losses (large margin defeats)
            embarrassing_losses = 0
            for stat, past_game in recent_games_vs_opponent:
                # Simplified: check if team lost by 20+ points
                if past_game.home_team_id == game.away_team_id:  # opponent was home
                    margin = (past_game.home_score or 0) - (past_game.away_score or 0)
                else:  # opponent was away
                    margin = (past_game.away_score or 0) - (past_game.home_score or 0)

                if margin >= 20:  # Embarrassing loss
                    embarrassing_losses += 1

            if embarrassing_losses >= 1:
                return 1.05  # 5% revenge boost

        return 1.0

    def _calculate_streak_motivation(self, player_id: int, game: Game) -> float:
        """Calculate motivation from personal/team streaks."""
        # Simplified streak motivation
        # In real implementation, would analyze player and team streaks
        return 1.02  # 2% boost for streak-related motivation