"""
Recent Form Calculator

Calculates recent performance trends for players.
"""
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session
from typing import Optional, Dict, List
from datetime import date, timedelta
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.season import Season
import statistics
import math


class FormCalculator:
    """Calculate recent form and trends for players."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_player_form(
        self,
        player_id: int,
        season_id: Optional[int] = None,
        last_n_games: int = 15
    ) -> Dict:
        """
        Calculate recent form for a player.
        
        Args:
            player_id: Player to analyze
            season_id: Season to analyze (default: current)
            last_n_games: Number of recent games to analyze
        
        Returns:
            Dict with form statistics
        """
        # Get season if not provided
        if season_id is None:
            season = self.db.query(Season).filter(
                Season.is_current == True
            ).first()
            if not season:
                raise ValueError("No current season found.")
            season_id = season.season_id
        
        # Get recent games with game dates for time weighting
        recent_stats_query = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).order_by(desc(Game.game_date)).limit(last_n_games).all()
        
        # Get game dates separately
        stats_with_dates = []
        for stat in recent_stats_query:
            game = self.db.query(Game).filter(Game.game_id == stat.game_id).first()
            game_date = game.game_date if game else date.today()
            stats_with_dates.append((stat, game_date))
        
        if not stats_with_dates:
            return {
                "games": 0,
                "trend": "insufficient_data"
            }
        
        # Apply time-weighted exponential decay
        # More recent games get higher weight
        # Weight = exp(-days_ago / decay_constant)
        # decay_constant = 7 means weight halves every 7 days
        today = date.today()
        decay_constant = 7.0  # Days for weight to decay by 1/e
        
        weighted_points = []
        weighted_rebounds = []
        weighted_assists = []
        weighted_minutes = []
        total_weight = 0.0
        
        for stat, game_date in stats_with_dates:
            days_ago = (today - game_date).days
            weight = math.exp(-days_ago / decay_constant)
            
            weighted_points.append(stat.points * weight)
            weighted_rebounds.append(stat.rebounds * weight)
            weighted_assists.append(stat.assists * weight)
            weighted_minutes.append(stat.minutes_played * weight)
            total_weight += weight
        
        # Calculate time-weighted averages
        if total_weight > 0:
            tw_avg_points = sum(weighted_points) / total_weight
            tw_avg_rebounds = sum(weighted_rebounds) / total_weight
            tw_avg_assists = sum(weighted_assists) / total_weight
            tw_avg_minutes = sum(weighted_minutes) / total_weight
        else:
            tw_avg_points = tw_avg_rebounds = tw_avg_assists = tw_avg_minutes = 0
        
        # Also calculate unweighted averages for comparison
        all_points = [s.points for s, _ in stats_with_dates]
        all_rebounds = [s.rebounds for s, _ in stats_with_dates]
        all_assists = [s.assists for s, _ in stats_with_dates]
        all_minutes = [s.minutes_played for s, _ in stats_with_dates]
        
        # Last 5, 10 games (unweighted for trend calculation)
        last_5 = stats_with_dates[:5] if len(stats_with_dates) >= 5 else stats_with_dates
        last_10 = stats_with_dates[:10] if len(stats_with_dates) >= 10 else stats_with_dates
        
        last_5_points = [s.points for s, _ in last_5]
        last_10_points = [s.points for s, _ in last_10]
        
        # Calculate trends
        trend = self._calculate_trend(all_points)
        
        # Calculate standard deviations
        std_dev_points = statistics.stdev(all_points) if len(all_points) > 1 else 0
        std_dev_rebounds = statistics.stdev(all_rebounds) if len(all_rebounds) > 1 else 0
        std_dev_assists = statistics.stdev(all_assists) if len(all_assists) > 1 else 0
        
        return {
            "games": len(stats_with_dates),
            "avg_points": round(sum(all_points) / len(all_points), 2) if all_points else 0,
            "avg_rebounds": round(sum(all_rebounds) / len(all_rebounds), 2) if all_rebounds else 0,
            "avg_assists": round(sum(all_assists) / len(all_assists), 2) if all_assists else 0,
            "avg_minutes": round(sum(all_minutes) / len(all_minutes), 2) if all_minutes else 0,
            # Time-weighted averages (more accurate for recent form)
            "tw_avg_points": round(tw_avg_points, 2),
            "tw_avg_rebounds": round(tw_avg_rebounds, 2),
            "tw_avg_assists": round(tw_avg_assists, 2),
            "tw_avg_minutes": round(tw_avg_minutes, 2),
            "last_5_avg_points": round(sum(last_5_points) / len(last_5_points), 2) if last_5_points else None,
            "last_10_avg_points": round(sum(last_10_points) / len(last_10_points), 2) if last_10_points else None,
            "std_dev_points": round(std_dev_points, 2),
            "std_dev_rebounds": round(std_dev_rebounds, 2),
            "std_dev_assists": round(std_dev_assists, 2),
            "trend": trend,
            "min_points": min(all_points) if all_points else 0,
            "max_points": max(all_points) if all_points else 0
        }
    
    def calculate_shooting_streak(
        self,
        player_id: int,
        season_id: Optional[int] = None,
        last_n_games: int = 10
    ) -> Dict:
        """
        Calculate player's recent shooting percentages vs season average.
        
        Returns:
            Dict with shooting percentages and adjustment factor for points
        """
        # Get season if not provided
        if season_id is None:
            season = self.db.query(Season).filter(
                Season.is_current == True
            ).first()
            if not season:
                return {'shooting_factor': 1.0}
            season_id = season.season_id
        
        # Get recent games with shooting stats
        recent_stats = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0,
                PlayerGameStat.field_goals_attempted > 0  # Must have attempted shots
            )
        ).order_by(desc(Game.game_date)).limit(last_n_games).all()
        
        if len(recent_stats) < 5:  # Need at least 5 games
            return {'shooting_factor': 1.0}
        
        # Calculate recent shooting percentages
        recent_fg_made = sum(s.field_goals_made for s in recent_stats)
        recent_fg_attempted = sum(s.field_goals_attempted for s in recent_stats)
        recent_3p_made = sum(s.three_pointers_made for s in recent_stats)
        recent_3p_attempted = sum(s.three_pointers_attempted for s in recent_stats)
        recent_ft_made = sum(s.free_throws_made for s in recent_stats)
        recent_ft_attempted = sum(s.free_throws_attempted for s in recent_stats)
        
        recent_fg_pct = recent_fg_made / recent_fg_attempted if recent_fg_attempted > 0 else 0
        recent_3p_pct = recent_3p_made / recent_3p_attempted if recent_3p_attempted > 0 else 0
        recent_ft_pct = recent_ft_made / recent_ft_attempted if recent_ft_attempted > 0 else 0
        
        # Get season averages
        all_season_stats = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0,
                PlayerGameStat.field_goals_attempted > 0
            )
        ).all()
        
        if len(all_season_stats) < 10:  # Need at least 10 games for season average
            return {'shooting_factor': 1.0}
        
        season_fg_made = sum(s.field_goals_made for s in all_season_stats)
        season_fg_attempted = sum(s.field_goals_attempted for s in all_season_stats)
        season_3p_made = sum(s.three_pointers_made for s in all_season_stats)
        season_3p_attempted = sum(s.three_pointers_attempted for s in all_season_stats)
        season_ft_made = sum(s.free_throws_made for s in all_season_stats)
        season_ft_attempted = sum(s.free_throws_attempted for s in all_season_stats)
        
        season_fg_pct = season_fg_made / season_fg_attempted if season_fg_attempted > 0 else 0
        season_3p_pct = season_3p_made / season_3p_attempted if season_3p_attempted > 0 else 0
        season_ft_pct = season_ft_made / season_ft_attempted if season_ft_attempted > 0 else 0
        
        # Calculate weighted shooting percentage difference
        # Weight FG% more heavily (most shots are 2-pointers)
        fg_diff = recent_fg_pct - season_fg_pct
        three_p_diff = recent_3p_pct - season_3p_pct
        ft_diff = recent_ft_pct - season_ft_pct
        
        # Weighted average: 60% FG, 30% 3P, 10% FT
        weighted_diff = (fg_diff * 0.6) + (three_p_diff * 0.3) + (ft_diff * 0.1)
        
        # Convert to adjustment factor
        # If shooting 5% better: +2-4% boost
        # If shooting 5% worse: -2-4% penalty
        if weighted_diff >= 0.05:  # 5% or more better
            shooting_factor = 1.04
        elif weighted_diff >= 0.03:  # 3-5% better
            shooting_factor = 1.02
        elif weighted_diff >= 0.01:  # 1-3% better
            shooting_factor = 1.01
        elif weighted_diff <= -0.05:  # 5% or more worse
            shooting_factor = 0.96
        elif weighted_diff <= -0.03:  # 3-5% worse
            shooting_factor = 0.98
        elif weighted_diff <= -0.01:  # 1-3% worse
            shooting_factor = 0.99
        else:
            shooting_factor = 1.0
        
        return {
            'recent_fg_pct': round(recent_fg_pct, 3),
            'season_fg_pct': round(season_fg_pct, 3),
            'recent_3p_pct': round(recent_3p_pct, 3),
            'season_3p_pct': round(season_3p_pct, 3),
            'recent_ft_pct': round(recent_ft_pct, 3),
            'season_ft_pct': round(season_ft_pct, 3),
            'weighted_diff': round(weighted_diff, 3),
            'shooting_factor': shooting_factor
        }
    
    def calculate_true_shooting_percentage(
        self,
        player_id: int,
        season_id: Optional[int] = None,
        last_n_games: int = 10
    ) -> Dict:
        """
        Calculate True Shooting Percentage (TS%) - more accurate than FG%.
        
        TS% = Points / (2 * (FGA + 0.44 * FTA))
        
        Returns:
            Dict with TS% and adjustment factor
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return {'ts_factor': 1.0}
            season_id = season.season_id
        
        # Get recent games
        recent_stats = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0,
                PlayerGameStat.field_goals_attempted > 0
            )
        ).order_by(desc(Game.game_date)).limit(last_n_games).all()
        
        if len(recent_stats) < 5:
            return {'ts_factor': 1.0}
        
        # Calculate recent TS%
        recent_points = sum(s.points or 0 for s in recent_stats)
        recent_fga = sum(s.field_goals_attempted or 0 for s in recent_stats)
        recent_fta = sum(s.free_throws_attempted or 0 for s in recent_stats)
        
        recent_ts_pct = recent_points / (2 * (recent_fga + 0.44 * recent_fta)) if (recent_fga + 0.44 * recent_fta) > 0 else 0
        
        # Get season TS%
        all_season_stats = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0,
                PlayerGameStat.field_goals_attempted > 0
            )
        ).all()
        
        if len(all_season_stats) < 10:
            return {'ts_factor': 1.0}
        
        season_points = sum(s.points or 0 for s in all_season_stats)
        season_fga = sum(s.field_goals_attempted or 0 for s in all_season_stats)
        season_fta = sum(s.free_throws_attempted or 0 for s in all_season_stats)
        
        season_ts_pct = season_points / (2 * (season_fga + 0.44 * season_fta)) if (season_fga + 0.44 * season_fta) > 0 else 0
        
        # Calculate adjustment factor
        ts_diff = recent_ts_pct - season_ts_pct
        
        # TS% is typically 0.50-0.60 for good players
        # A 0.05 difference is significant
        if ts_diff >= 0.05:  # 5% better recently
            ts_factor = 1.03
        elif ts_diff >= 0.03:  # 3% better
            ts_factor = 1.02
        elif ts_diff >= 0.01:  # 1% better
            ts_factor = 1.01
        elif ts_diff <= -0.05:  # 5% worse
            ts_factor = 0.97
        elif ts_diff <= -0.03:  # 3% worse
            ts_factor = 0.98
        elif ts_diff <= -0.01:  # 1% worse
            ts_factor = 0.99
        else:
            ts_factor = 1.0
        
        return {
            'recent_ts_pct': round(recent_ts_pct, 3),
            'season_ts_pct': round(season_ts_pct, 3),
            'ts_diff': round(ts_diff, 3),
            'ts_factor': ts_factor
        }
    
    def _calculate_trend(self, points_list: List[int]) -> str:
        """
        Calculate if player is improving, declining, or stable.
        
        Returns:
            "improving", "declining", or "stable"
        """
        if len(points_list) < 5:
            return "insufficient_data"
        
        # Split into first half and second half
        mid = len(points_list) // 2
        first_half = points_list[mid:]
        second_half = points_list[:mid]
        
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        
        # Threshold: 5% change
        change = (second_avg - first_avg) / first_avg if first_avg > 0 else 0
        
        if change > 0.05:
            return "improving"
        elif change < -0.05:
            return "declining"
        else:
            return "stable"
    
    def calculate_season_averages(
        self,
        player_id: int,
        season_id: Optional[int] = None
    ) -> Dict:
        """
        Calculate full season averages for a player.
        
        Returns:
            Dict with season statistics
        """
        # Get season if not provided
        if season_id is None:
            season = self.db.query(Season).filter(
                Season.is_current == True
            ).first()
            if not season:
                raise ValueError("No current season found.")
            season_id = season.season_id
        
        # Get all games
        all_stats = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).all()
        
        if not all_stats:
            return {"games": 0}
        
        all_points = [s.points for s in all_stats]
        all_rebounds = [s.rebounds for s in all_stats]
        all_assists = [s.assists for s in all_stats]
        all_minutes = [s.minutes_played for s in all_stats]
        
        return {
            "games": len(all_stats),
            "avg_points": round(sum(all_points) / len(all_points), 2),
            "avg_rebounds": round(sum(all_rebounds) / len(all_rebounds), 2),
            "avg_assists": round(sum(all_assists) / len(all_assists), 2),
            "avg_minutes": round(sum(all_minutes) / len(all_minutes), 2),
            "total_points": sum(all_points),
            "total_rebounds": sum(all_rebounds),
            "total_assists": sum(all_assists)
        }

