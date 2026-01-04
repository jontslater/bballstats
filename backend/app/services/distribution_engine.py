"""
Distribution Engine

Calculates base distributions from historical player performance data.
"""
import numpy as np
from scipy import stats
from sqlalchemy import and_, or_, desc, func
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Tuple
from datetime import date
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.player import Player
from app.models.season import Season
from app.models.lineup import Lineup


class DistributionEngine:
    """Calculate base distributions from historical data."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_base_distribution(
        self,
        player_id: int,
        stat_type: str,  # 'points', 'rebounds', 'assists', 'minutes'
        projected_minutes: Optional[float] = None,
        is_starter: Optional[bool] = None,
        season_ids: Optional[List[int]] = None,
        min_games: int = 15
    ) -> Optional[Dict]:
        """
        Calculate base distribution for a player's stat.
        
        Args:
            player_id: Player ID
            stat_type: Type of stat ('points', 'rebounds', 'assists', 'minutes')
            projected_minutes: Projected minutes (for filtering)
            is_starter: Whether player is starter (for filtering)
            season_ids: List of season IDs to include (default: current + previous)
            min_games: Minimum games required
        
        Returns:
            Dict with distribution data or None if insufficient data
        """
        # Get seasons if not provided
        if season_ids is None:
            seasons = self.db.query(Season).filter(
                or_(
                    Season.is_current == True,
                    Season.is_previous == True
                )
            ).all()
            season_ids = [s.season_id for s in seasons]
        
        # Get historical game stats
        query = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id.in_(season_ids),
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        )
        
        # Filter by minutes (≥65% of projected if provided) - relaxed threshold
        if projected_minutes:
            min_minutes = projected_minutes * 0.65
            query = query.filter(PlayerGameStat.minutes_played >= min_minutes)
        
        # Filter by role (starter vs bench) if provided
        if is_starter is not None:
            # Get games where player was a starter
            if is_starter:
                starter_game_ids = self.db.query(Lineup.game_id).filter(
                    and_(
                        Lineup.player_id == player_id,
                        Lineup.is_starter == True
                    )
                ).subquery()
                query = query.filter(PlayerGameStat.game_id.in_(
                    self.db.query(starter_game_ids.c.game_id)
                ))
            else:
                # Player was not a starter
                starter_game_ids = self.db.query(Lineup.game_id).filter(
                    and_(
                        Lineup.player_id == player_id,
                        Lineup.is_starter == True
                    )
                ).subquery()
                query = query.filter(~PlayerGameStat.game_id.in_(
                    self.db.query(starter_game_ids.c.game_id)
                ))
        
        stats_list = query.order_by(desc(Game.game_date)).all()
        
        if len(stats_list) < min_games:
            return None
        
        # Extract stat values
        stat_values = []
        for stat in stats_list:
            if stat_type == 'points':
                stat_values.append(stat.points)
            elif stat_type == 'rebounds':
                stat_values.append(stat.rebounds)
            elif stat_type == 'assists':
                stat_values.append(stat.assists)
            elif stat_type == 'minutes':
                stat_values.append(stat.minutes_played)
            else:
                raise ValueError(f"Unknown stat_type: {stat_type}")
        
        if not stat_values:
            return None
        
        # Convert to numpy array
        values = np.array(stat_values)
        
        # Calculate base statistics
        base_mean = float(np.mean(values))
        base_std = float(np.std(values, ddof=1))  # Sample standard deviation
        
        # Calculate percentiles
        percentiles = {
            10: float(np.percentile(values, 10)),
            20: float(np.percentile(values, 20)),
            25: float(np.percentile(values, 25)),
            50: float(np.percentile(values, 50)),  # Median
            75: float(np.percentile(values, 75)),
            80: float(np.percentile(values, 80)),
            85: float(np.percentile(values, 85)),
            90: float(np.percentile(values, 90))
        }
        
        # Calculate coefficient of variation (for volatility assessment)
        cv = (base_std / base_mean) if base_mean > 0 else 0
        
        return {
            'mean': round(base_mean, 2),
            'std_dev': round(base_std, 2),
            'percentiles': percentiles,
            'sample_size': len(values),
            'cv': round(cv, 3),  # Coefficient of variation
            'min': float(np.min(values)),
            'max': float(np.max(values))
        }
    
    def get_historical_avg_minutes(
        self,
        player_id: int,
        season_ids: Optional[List[int]] = None,
        recent_games: Optional[int] = None
    ) -> Optional[float]:
        """
        Get historical average minutes for a player.
        
        Args:
            player_id: Player ID
            season_ids: List of season IDs (default: current + previous)
            recent_games: Only use last N games (optional)
        
        Returns:
            Average minutes or None
        """
        # Get seasons if not provided
        if season_ids is None:
            seasons = self.db.query(Season).filter(
                or_(
                    Season.is_current == True,
                    Season.is_previous == True
                )
            ).all()
            season_ids = [s.season_id for s in seasons]
        
        query = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id.in_(season_ids),
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).order_by(desc(Game.game_date))
        
        if recent_games:
            query = query.limit(recent_games)
        
        stats_list = query.all()
        
        if not stats_list:
            return None
        
        # Weight recent games more heavily (exponential decay)
        # More recent games have higher weight
        total_weight = 0.0
        weighted_sum = 0.0
        
        for i, stat in enumerate(stats_list):
            # Exponential decay: 0.95^0 = 1.0 (most recent), 0.95^1 = 0.95, etc.
            weight = 0.95 ** i
            weighted_sum += stat.minutes_played * weight
            total_weight += weight
        
        if total_weight > 0:
            avg_minutes = weighted_sum / total_weight
        else:
            # Fallback to simple average if no weights
            avg_minutes = sum(s.minutes_played for s in stats_list) / len(stats_list)
        
        return round(avg_minutes, 2)
    
    def get_historical_usage_rate(
        self,
        player_id: int,
        season_ids: Optional[List[int]] = None
    ) -> Optional[float]:
        """
        Get historical usage rate for a player.
        
        Uses proper NBA usage rate formula:
        Usage Rate = 100 * ((FGA + 0.44 * FTA + TO) * (Team Minutes / 5)) / (Player Minutes * (Team FGA + 0.44 * Team FTA + Team TO))
        
        Simplified version (when team stats not available):
        Usage Rate ≈ (FGA + 0.44 * FTA + TO) / (Player Minutes * Pace Factor)
        
        Returns:
            Average usage rate (0-1 scale) or None
        """
        # Get seasons if not provided
        if season_ids is None:
            seasons = self.db.query(Season).filter(
                or_(
                    Season.is_current == True,
                    Season.is_previous == True
                )
            ).all()
            season_ids = [s.season_id for s in seasons]
        
        query = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id.in_(season_ids),
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        )
        
        stats_list = query.all()
        
        if not stats_list:
            return None
        
        # Calculate usage rate for each game
        usage_rates = []
        for stat in stats_list:
            if stat.minutes_played == 0:
                continue
            
            # Get team stats for this game
            team_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == stat.game_id,
                    PlayerGameStat.team_id == stat.team_id
                )
            ).all()
            
            # Calculate team totals
            team_fga = sum(s.field_goals_attempted or 0 for s in team_stats)
            team_fta = sum(s.free_throws_attempted or 0 for s in team_stats)
            team_to = sum(s.turnovers or 0 for s in team_stats)
            team_minutes = sum(s.minutes_played for s in team_stats)
            
            # Player stats
            player_fga = stat.field_goals_attempted or 0
            player_fta = stat.free_throws_attempted or 0
            player_to = stat.turnovers or 0
            player_minutes = stat.minutes_played
            
            # Calculate usage rate using proper formula
            if team_minutes > 0 and (team_fga + 0.44 * team_fta + team_to) > 0:
                # Full formula
                usage_rate = (
                    (player_fga + 0.44 * player_fta + player_to) * (team_minutes / 5)
                ) / (
                    player_minutes * (team_fga + 0.44 * team_fta + team_to)
                )
                usage_rates.append(usage_rate)
            else:
                # Fallback: simplified calculation
                # Estimate based on player's share of team possessions
                # Assuming average pace of 100, each minute ≈ 2 possessions
                estimated_possessions = player_minutes * 2
                if estimated_possessions > 0:
                    player_possessions = player_fga + 0.44 * player_fta + player_to
                    usage_rate = player_possessions / estimated_possessions
                    usage_rates.append(usage_rate)
        
        if not usage_rates:
            return None
        
        # Return average usage rate (0-1 scale, multiply by 100 for percentage)
        avg_usage = sum(usage_rates) / len(usage_rates)
        return round(avg_usage, 3)

