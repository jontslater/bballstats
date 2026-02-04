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
        stat_type: str,  # 'points', 'rebounds', 'assists', 'minutes' (NBA) or NFL stats
        sport: str = 'NBA',  # 'NBA' or 'NFL'
        projected_minutes: Optional[float] = None,
        is_starter: Optional[bool] = None,
        season_ids: Optional[List[int]] = None,
        min_games: int = 15
    ) -> Optional[Dict]:
        """
        Calculate base distribution for a player's stat.
        
        Args:
            player_id: Player ID
            stat_type: Type of stat (NBA: 'points', 'rebounds', 'assists', 'minutes'; NFL: 'passing_yards', etc.)
            sport: Sport type ('NBA' or 'NFL')
            projected_minutes: Projected minutes/snaps (for filtering)
            is_starter: Whether player is starter (for filtering)
            season_ids: List of season IDs to include (default: current + previous)
            min_games: Minimum games required
        
        Returns:
            Dict with distribution data or None if insufficient data
        """
        # Get player to determine sport if not provided
        player = self.db.query(Player).filter(Player.player_id == player_id).first()
        if player:
            sport = player.sport
        
        # Get seasons if not provided
        if season_ids is None:
            # Get current season and previous season
            current_season = self.db.query(Season).filter(
                and_(
                    Season.sport == sport,
                    Season.is_current == True
                )
            ).first()
            
            seasons = []
            if current_season:
                seasons.append(current_season)
                # Get previous season (current year - 1)
                prev_year = int(current_season.season_year.split('-')[0]) - 1
                prev_season = self.db.query(Season).filter(
                    and_(
                        Season.sport == sport,
                        Season.season_year.like(f'{prev_year}%')
                    )
                ).first()
                if prev_season:
                    seasons.append(prev_season)
            
            season_ids = [s.season_id for s in seasons] if seasons else []
        
        # Get historical game stats
        query = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.sport == sport,
                PlayerGameStat.player_id == player_id,
                Game.season_id.in_(season_ids),
                Game.game_status == 'finished'
            )
        )
        
        # Filter by time played (minutes for NBA, snaps for NFL)
        # For NFL, we might not have snap data, so we'll use a different filter
        if sport == 'NBA':
            query = query.filter(PlayerGameStat.minutes_played > 0)
            if projected_minutes:
                min_minutes = projected_minutes * 0.65
                query = query.filter(PlayerGameStat.minutes_played >= min_minutes)
        else:  # NFL
            # For NFL, filter by snaps if available, otherwise allow all
            # We'll filter out players with no relevant stats later
            if projected_minutes:  # projected_minutes might represent snaps
                # If we have snap data, filter by it
                # For now, we'll be more lenient and filter in stat extraction
                pass
        
        # Filter by role (starter vs bench) if provided
        if is_starter is not None:
            # Get games where player was a starter
            if is_starter:
                starter_game_ids = self.db.query(Lineup.game_id).filter(
                    and_(
                        Lineup.sport == sport,
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
                        Lineup.sport == sport,
                        Lineup.player_id == player_id,
                        Lineup.is_starter == True
                    )
                ).subquery()
                query = query.filter(~PlayerGameStat.game_id.in_(
                    self.db.query(starter_game_ids.c.game_id)
                ))
        
        stats_list = query.order_by(desc(Game.game_date)).all()
        
        # Extract stat values (sport-aware)
        stat_values = []
        for stat in stats_list:
            value = None
            
            if sport == 'NBA':
                # NBA stats
                if stat_type == 'points':
                    value = stat.points
                elif stat_type == 'rebounds':
                    value = stat.rebounds
                elif stat_type == 'assists':
                    value = stat.assists
                elif stat_type == 'three_pointers_made':
                    value = stat.three_pointers_made
                elif stat_type == 'minutes':
                    value = stat.minutes_played
                elif stat_type == 'pts+ast+reb':
                    # PAR combo stat: points + assists + rebounds
                    value = (stat.points or 0) + (stat.assists or 0) + (stat.rebounds or 0)
                else:
                    raise ValueError(f"Unknown NBA stat_type: {stat_type}")
            else:  # NFL
                # NFL stats
                if stat_type == 'passing_yards':
                    value = stat.passing_yards
                elif stat_type == 'passing_tds':
                    value = stat.passing_tds
                elif stat_type == 'interceptions':
                    value = stat.interceptions
                elif stat_type == 'completions':
                    value = stat.completions
                elif stat_type == 'attempts':
                    value = stat.pass_attempts
                elif stat_type == 'rushing_yards':
                    value = stat.rushing_yards
                elif stat_type == 'rushing_tds':
                    value = stat.rushing_tds
                elif stat_type == 'rushing_attempts':
                    value = stat.rushing_attempts
                elif stat_type == 'receptions':
                    value = stat.receptions
                elif stat_type == 'receiving_yards':
                    value = stat.receiving_yards
                elif stat_type == 'receiving_tds':
                    value = stat.receiving_tds
                elif stat_type == 'targets':
                    value = stat.targets
                elif stat_type == 'snaps_played':
                    value = stat.snaps_played
                elif stat_type == 'snap_percentage':
                    value = stat.snap_percentage
                else:
                    raise ValueError(f"Unknown NFL stat_type: {stat_type}")
            
            # Only add non-null values (NFL players might not have stats for some stat types)
            if value is not None:
                stat_values.append(value)
        
        # For NFL, filter out players with insufficient data
        # (e.g., QB might not have rushing stats)
        if len(stat_values) < min_games:
            return None
        
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
        sport: str = 'NBA',
        season_ids: Optional[List[int]] = None,
        recent_games: Optional[int] = None,
        only_starters: bool = False
    ) -> Optional[float]:
        """
        Get historical average minutes/snaps for a player.
        
        Args:
            player_id: Player ID
            sport: Sport type ('NBA' or 'NFL')
            season_ids: List of season IDs (default: current + previous)
            recent_games: Only use last N games (optional)
            only_starters: If True, only include games where player was a starter
        
        Returns:
            Average minutes (NBA) or snaps (NFL) or None
        """
        # Get player to determine sport if not provided
        player = self.db.query(Player).filter(Player.player_id == player_id).first()
        if player:
            sport = player.sport
        
        # Get seasons if not provided
        if season_ids is None:
            # Get current season and previous season
            current_season = self.db.query(Season).filter(
                and_(
                    Season.sport == sport,
                    Season.is_current == True
                )
            ).first()
            
            seasons = []
            if current_season:
                seasons.append(current_season)
                # Get previous season (current year - 1)
                prev_year = int(current_season.season_year.split('-')[0]) - 1
                prev_season = self.db.query(Season).filter(
                    and_(
                        Season.sport == sport,
                        Season.season_year.like(f'{prev_year}%')
                    )
                ).first()
                if prev_season:
                    seasons.append(prev_season)
            
            season_ids = [s.season_id for s in seasons] if seasons else []
        
        query = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.sport == sport,
                PlayerGameStat.player_id == player_id,
                Game.season_id.in_(season_ids) if season_ids else False,
                Game.game_status == 'finished'
            )
        ).order_by(desc(Game.game_date))
        
        # Filter by time played
        if sport == 'NBA':
            query = query.filter(PlayerGameStat.minutes_played > 0)
        else:  # NFL - prefer snaps if available
            # For NFL, we'll check both snaps and minutes
            # But for now, we'll allow all records and filter by snaps when available
            pass
        
        if recent_games:
            query = query.limit(recent_games * 2 if only_starters else recent_games)  # Get more games if filtering by starters
        
        stats_list = query.all()
        
        if not stats_list:
            return None
        
        # Filter by starter status if requested
        if only_starters:
            from app.models.lineup import Lineup
            # Get game IDs where player was a starter (from Lineup table)
            starter_game_ids = {
                l.game_id for l in self.db.query(Lineup).filter(
                    and_(
                        Lineup.player_id == player_id,
                        Lineup.is_starter == True
                    )
                ).all()
            }
            
            # Filter stats_list to only games where player was a starter
            # Also infer starter status from minutes (>=25 minutes = likely starter if no lineup data)
            filtered_stats = []
            for stat in stats_list:
                is_starter = False
                
                # Check Lineup table first (most accurate)
                if stat.game_id in starter_game_ids:
                    is_starter = True
                else:
                    # Infer from minutes: >=25 minutes = likely starter (NBA)
                    # For NFL, use snaps if available, otherwise minutes
                    if sport == 'NBA':
                        if stat.minutes_played and stat.minutes_played >= 25:
                            is_starter = True
                    else:  # NFL
                        if stat.snaps_played and stat.snaps_played >= 40:  # ~60% of snaps
                            is_starter = True
                        elif stat.minutes_played and stat.minutes_played >= 40:
                            is_starter = True
                
                if is_starter:
                    filtered_stats.append(stat)
            
            stats_list = filtered_stats[:recent_games] if recent_games else filtered_stats  # Limit after filtering
        
        if not stats_list:
            return None
        
        # Weight recent games more heavily (exponential decay)
        total_weight = 0.0
        weighted_sum = 0.0
        
        for i, stat in enumerate(stats_list):
            # Exponential decay: 0.95^0 = 1.0 (most recent), 0.95^1 = 0.95, etc.
            weight = 0.95 ** i
            
            # Get time value based on sport
            if sport == 'NBA':
                time_value = stat.minutes_played or 0
            else:  # NFL
                # Prefer snaps, fallback to estimated minutes
                time_value = stat.snaps_played if stat.snaps_played else (stat.minutes_played or 0)
            
            if time_value > 0:
                weighted_sum += time_value * weight
                total_weight += weight
        
        if total_weight > 0:
            avg_time = weighted_sum / total_weight
        else:
            # Fallback to simple average
            time_values = []
            for stat in stats_list:
                if sport == 'NBA':
                    time_values.append(stat.minutes_played or 0)
                else:
                    time_values.append(stat.snaps_played if stat.snaps_played else (stat.minutes_played or 0))
            avg_time = sum(time_values) / len(time_values) if time_values else 0
        
        return round(avg_time, 2) if avg_time > 0 else None
    
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
            # Get current season and previous season
            current_season = self.db.query(Season).filter(
                Season.is_current == True
            ).first()
            
            seasons = []
            if current_season:
                seasons.append(current_season)
                # Get previous season (current year - 1)
                prev_year = int(current_season.season_year.split('-')[0]) - 1
                prev_season = self.db.query(Season).filter(
                    Season.season_year.like(f'{prev_year}%')
                ).first()
                if prev_season:
                    seasons.append(prev_season)
            
            season_ids = [s.season_id for s in seasons] if seasons else []
        
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

