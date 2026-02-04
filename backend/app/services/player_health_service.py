"""
Player Health & Fatigue Service

Advanced analysis of player health, fatigue, load management, and injury recovery.
Factors in rest patterns, minute distribution, and performance degradation.
"""

from sqlalchemy import and_, func, desc
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Tuple
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.player import Player
from datetime import timedelta
import statistics


class PlayerHealthService:
    """Analyze player health, fatigue, and load management factors."""

    def __init__(self, db: Session):
        self.db = db
        self.fatigue_threshold_high = 45  # Minutes above this = high fatigue
        self.fatigue_threshold_extreme = 50  # Minutes above this = extreme fatigue
        self.rest_days_optimal = 3  # Days between games for optimal recovery
        self.back_to_back_penalty = 0.05  # 5% penalty for B2B games

    def calculate_health_fatigue_factor(
        self,
        player_id: int,
        game_id: int,
        season_id: Optional[int] = None,
        projected_minutes: float = 0
    ) -> Dict[str, float]:
        """
        Calculate comprehensive health and fatigue factors.

        Args:
            player_id: Player to analyze
            game_id: Current game
            season_id: Season for analysis
            projected_minutes: Expected minutes in current game

        Returns:
            Dict with health/fatigue factors and adjustments
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return {'health_factor': 1.0, 'fatigue_factor': 1.0, 'overall_factor': 1.0}
            season_id = season.season_id

        # Get current game
        current_game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not current_game:
            return {'health_factor': 1.0, 'fatigue_factor': 1.0, 'overall_factor': 1.0}

        # Analyze recent workload
        workload_analysis = self._analyze_recent_workload(player_id, current_game, season_id)

        # Calculate fatigue factor
        fatigue_factor = self._calculate_fatigue_factor(workload_analysis, projected_minutes)

        # Analyze rest patterns
        rest_factor = self._calculate_rest_factor(player_id, current_game, season_id)

        # Load management analysis
        load_factor = self._calculate_load_management_factor(workload_analysis, season_id)

        # Injury recovery factor (simplified - would need injury data)
        injury_factor = self._calculate_injury_recovery_factor(player_id, current_game)

        # Combine all factors
        overall_factor = fatigue_factor * rest_factor * load_factor * injury_factor

        return {
            'fatigue_factor': round(fatigue_factor, 3),
            'rest_factor': round(rest_factor, 3),
            'load_factor': round(load_factor, 3),
            'injury_factor': round(injury_factor, 3),
            'overall_factor': round(overall_factor, 3),
            'workload_analysis': workload_analysis
        }

    def _analyze_recent_workload(
        self,
        player_id: int,
        current_game: Game,
        season_id: int,
        lookback_days: int = 21
    ) -> Dict[str, any]:
        """
        Analyze player's recent workload patterns.
        """
        lookback_date = current_game.game_date - timedelta(days=lookback_days)

        # Get recent games
        recent_games = self.db.query(PlayerGameStat, Game).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_date >= lookback_date,
                Game.game_date < current_game.game_date,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).order_by(Game.game_date).all()

        if not recent_games:
            return {
                'games_played': 0,
                'avg_minutes': 0,
                'total_minutes': 0,
                'high_minute_games': 0,
                'back_to_back_games': 0,
                'rest_days_avg': 3.0
            }

        # Analyze workload
        minutes_list = [stat.minutes_played for stat, game in recent_games]
        game_dates = [game.game_date for stat, game in recent_games]

        # Calculate stats
        avg_minutes = sum(minutes_list) / len(minutes_list)
        total_minutes = sum(minutes_list)
        high_minute_games = sum(1 for m in minutes_list if m >= self.fatigue_threshold_high)

        # Calculate rest days between games
        rest_days = []
        for i in range(1, len(game_dates)):
            days_diff = (game_dates[i] - game_dates[i-1]).days
            rest_days.append(days_diff)

        avg_rest_days = sum(rest_days) / len(rest_days) if rest_days else 3.0

        # Count back-to-back games (1 day apart)
        back_to_back_games = sum(1 for days in rest_days if days == 1)

        return {
            'games_played': len(recent_games),
            'avg_minutes': round(avg_minutes, 1),
            'total_minutes': total_minutes,
            'high_minute_games': high_minute_games,
            'back_to_back_games': back_to_back_games,
            'rest_days_avg': round(avg_rest_days, 1),
            'minutes_trend': self._calculate_minutes_trend(minutes_list),
            'workload_consistency': self._calculate_workload_consistency(minutes_list)
        }

    def _calculate_fatigue_factor(
        self,
        workload_analysis: Dict,
        projected_minutes: float
    ) -> float:
        """
        Calculate fatigue factor based on workload and projected minutes.
        """
        if workload_analysis['games_played'] == 0:
            return 1.0

        fatigue_factor = 1.0

        # Recent average minutes impact
        avg_minutes = workload_analysis['avg_minutes']
        if avg_minutes >= self.fatigue_threshold_extreme:
            fatigue_factor *= 0.85  # 15% penalty for extreme workload
        elif avg_minutes >= self.fatigue_threshold_high:
            fatigue_factor *= 0.92  # 8% penalty for high workload
        elif avg_minutes <= 20:
            fatigue_factor *= 1.03  # 3% boost for light workload

        # High minute games impact
        high_minute_ratio = workload_analysis['high_minute_games'] / workload_analysis['games_played']
        if high_minute_ratio >= 0.6:  # 60%+ of games with high minutes
            fatigue_factor *= 0.88
        elif high_minute_ratio >= 0.4:  # 40%+ of games with high minutes
            fatigue_factor *= 0.94

        # Back-to-back games impact
        back_to_back_ratio = workload_analysis['back_to_back_games'] / max(1, workload_analysis['games_played'] - 1)
        fatigue_factor *= (1.0 - back_to_back_ratio * self.back_to_back_penalty)

        # Projected minutes impact
        if projected_minutes >= self.fatigue_threshold_extreme:
            fatigue_factor *= 0.90
        elif projected_minutes >= self.fatigue_threshold_high:
            fatigue_factor *= 0.95

        # Workload consistency (inconsistent minutes can cause fatigue)
        consistency = workload_analysis.get('workload_consistency', 1.0)
        if consistency < 0.7:  # Inconsistent minutes
            fatigue_factor *= 0.96

        return max(0.75, min(1.10, fatigue_factor))  # Clamp to reasonable range

    def _calculate_rest_factor(self, player_id: int, current_game: Game, season_id: int) -> float:
        """
        Calculate rest factor based on days since last game.
        """
        # Find last game played
        last_game = self.db.query(Game).join(PlayerGameStat).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_date < current_game.game_date,
                Game.game_status == 'finished'
            )
        ).order_by(desc(Game.game_date)).first()

        if not last_game:
            return 1.05  # Well-rested (first game)

        rest_days = (current_game.game_date - last_game.game_date).days

        if rest_days >= self.rest_days_optimal:
            return 1.08  # Optimal rest = 8% boost
        elif rest_days >= 2:
            return 1.05  # Good rest = 5% boost
        elif rest_days == 1:
            return 0.95  # Back-to-back = 5% penalty
        elif rest_days == 0:
            return 0.85  # Same day double header = 15% penalty
        else:
            return 1.02  # Light rest = slight boost

    def _calculate_load_management_factor(
        self,
        workload_analysis: Dict,
        season_id: int
    ) -> float:
        """
        Calculate load management factor based on season-long patterns.
        """
        # This is a simplified version. In a full implementation, would:
        # - Analyze season-long minute distribution
        # - Check for planned rest patterns
        # - Consider age and injury history
        # - Look for coaching tendencies

        if workload_analysis['games_played'] == 0:
            return 1.0

        # Check for recent load reduction (possible injury management)
        minutes_trend = workload_analysis.get('minutes_trend', 0)
        if minutes_trend < -0.1:  # Significant minute reduction
            return 0.90  # Penalty for load management (player might be limited)

        # Check for extreme workloads (possible overuse)
        if workload_analysis['avg_minutes'] >= self.fatigue_threshold_extreme:
            games_played = workload_analysis['games_played']
            if games_played >= 5:  # Sustained heavy workload
                return 0.93  # Slight penalty for potential overuse

        return 1.0

    def _calculate_injury_recovery_factor(self, player_id: int, current_game: Game) -> float:
        """
        Calculate injury recovery factor.
        This is simplified - in a real system would need injury tracking.
        """
        # Placeholder for injury analysis
        # Would check:
        # - Recent injury status
        # - Time since injury
        # - Recovery patterns
        # - Performance after similar injuries

        return 1.0  # No injury impact assumed

    def _calculate_minutes_trend(self, minutes_list: List[float]) -> float:
        """
        Calculate trend in minutes (positive = increasing, negative = decreasing).
        """
        if len(minutes_list) < 3:
            return 0.0

        # Simple linear trend
        n = len(minutes_list)
        x = list(range(n))
        y = minutes_list

        # Calculate slope using simple linear regression
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_xx = sum(xi * xi for xi in x)

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
        avg_minutes = sum_y / n

        # Return normalized trend (-1 to 1, where 1 = strongly increasing)
        return slope / avg_minutes if avg_minutes > 0 else 0.0

    def _calculate_workload_consistency(self, minutes_list: List[float]) -> float:
        """
        Calculate consistency of workload (1.0 = very consistent, 0.0 = very inconsistent).
        """
        if len(minutes_list) < 3:
            return 1.0

        avg_minutes = sum(minutes_list) / len(minutes_list)
        if avg_minutes == 0:
            return 1.0

        # Calculate coefficient of variation (lower = more consistent)
        variance = sum((m - avg_minutes) ** 2 for m in minutes_list) / len(minutes_list)
        std_dev = variance ** 0.5
        cv = std_dev / avg_minutes if avg_minutes > 0 else 0

        # Convert to consistency score (lower CV = higher consistency)
        consistency = max(0.0, 1.0 - cv)
        return round(consistency, 3)