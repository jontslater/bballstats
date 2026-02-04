"""
Advanced Analytics Service

Calculates advanced NBA statistics and metrics for improved predictions.
Includes PER, TS%, USG%, eFG%, and other sophisticated basketball analytics.
"""

from sqlalchemy import and_, func, desc, case
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Tuple
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
# Team stats calculated from player game stats
from app.models.player import Player
import statistics
import math


class AdvancedAnalyticsService:
    """Calculate advanced NBA analytics for players and teams."""

    def __init__(self, db: Session):
        self.db = db

    def calculate_player_advanced_stats(
        self,
        player_id: int,
        season_id: Optional[int] = None,
        last_n_games: Optional[int] = None
    ) -> Dict[str, float]:
        """
        Calculate comprehensive advanced statistics for a player.

        Args:
            player_id: Player to analyze
            season_id: Season to analyze
            last_n_games: Limit to last N games (None for season total)

        Returns:
            Dict of advanced statistics
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return {}
            season_id = season.season_id

        # Get player stats
        query = self.db.query(PlayerGameStat).join(Game).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        )

        if last_n_games:
            query = query.order_by(desc(Game.game_date)).limit(last_n_games)
        else:
            query = query.order_by(Game.game_date)

        player_stats = query.all()

        if not player_stats:
            return {}

        # Calculate team stats from player stats
        game_ids = [stat.game_id for stat in player_stats]
        team_stats = self._calculate_team_stats_from_player_stats(game_ids, player_id)

        # Aggregate statistics
        totals = self._aggregate_player_stats(player_stats, team_stats)

        # Calculate advanced metrics
        advanced_stats = {}

        # Basic counting stats
        games_played = len(player_stats)
        advanced_stats['games_played'] = games_played

        if games_played == 0:
            return advanced_stats

        # Minutes per game
        advanced_stats['mpg'] = totals['minutes'] / games_played

        # True Shooting Percentage (TS%)
        # TS% = Points / (2 * (FGA + 0.44 * FTA))
        if totals['fga'] + (0.44 * totals['fta']) > 0:
            advanced_stats['ts_percent'] = (totals['points'] / (2 * (totals['fga'] + 0.44 * totals['fta']))) * 100

        # Effective Field Goal Percentage (eFG%)
        # eFG% = (FGM + 0.5 * 3PM) / FGA
        if totals['fga'] > 0:
            advanced_stats['efg_percent'] = ((totals['fgm'] + 0.5 * totals['tpm']) / totals['fga']) * 100

        # Usage Rate (USG%)
        # USG% = (FGA + 0.44 * FTA + TOV) / (MP / (TmMP / 5)) / Possessions
        # Simplified version for our data
        player_possessions = totals['fga'] + (0.44 * totals['fta']) + totals['tov']
        team_possessions = totals['team_possessions']

        if team_possessions > 0 and totals['minutes'] > 0:
            minutes_factor = totals['minutes'] / (totals['team_minutes'] / 5) if totals['team_minutes'] > 0 else 1
            advanced_stats['usg_percent'] = (player_possessions / team_possessions) * minutes_factor * 100

        # Assist Percentage (AST%)
        # AST% = 100 * AST / (((MP / (TmMP / 5)) * TmFG) - FG)
        if totals['team_fgm'] > totals['fgm'] and totals['team_minutes'] > 0:
            ast_factor = totals['minutes'] / (totals['team_minutes'] / 5)
            team_fg_minus_player = totals['team_fgm'] - totals['fgm']
            if team_fg_minus_player > 0:
                advanced_stats['ast_percent'] = (totals['ast'] / (ast_factor * team_fg_minus_player)) * 100

        # Rebound Percentage (REB%)
        # REB% = 100 * (TRB * (TmMP / 5)) / (MP * (TmTRB + OppTRB))
        if totals['minutes'] > 0 and totals['team_minutes'] > 0:
            reb_factor = totals['minutes'] / (totals['team_minutes'] / 5)
            total_rebounds = totals['team_trb'] + totals['opp_trb']
            if total_rebounds > 0:
                advanced_stats['reb_percent'] = (totals['trb'] * reb_factor / total_rebounds) * 100

        # Player Efficiency Rating (PER) - Simplified version
        # PER = (1 / MP) * [3P + REB + AST + STL + BLK - (FGA - FGM) - (FTA - FTM) - TOV]
        if totals['minutes'] > 0:
            per_components = (
                totals['tpm'] + totals['trb'] + totals['ast'] + totals['stl'] + totals['blk']
                - (totals['fga'] - totals['fgm'])
                - (totals['fta'] - totals['ftm'])
                - totals['tov']
            )
            advanced_stats['per'] = (per_components / totals['minutes']) * 48  # Per 48 minutes

        # Pace-adjusted metrics
        if totals['team_possessions'] > 0 and games_played > 0:
            possessions_per_game = totals['team_possessions'] / games_played

            # Points per 100 possessions
            advanced_stats['pts_per_100'] = (totals['points'] / totals['team_possessions']) * 100

            # True shooting per 100 possessions
            if 'ts_percent' in advanced_stats:
                advanced_stats['ts_per_100'] = advanced_stats['ts_percent']

        # Round all percentages to 1 decimal place
        for key, value in advanced_stats.items():
            if isinstance(value, float) and ('percent' in key or 'per_' in key):
                advanced_stats[key] = round(value, 1)
            elif isinstance(value, float):
                advanced_stats[key] = round(value, 2)

        return advanced_stats

    def _calculate_team_stats_from_player_stats(self, game_ids: List[int], exclude_player_id: int) -> Dict[int, Dict[str, float]]:
        """
        Calculate team stats from player game stats for given games.

        Returns:
            Dict of game_id -> team stats
        """
        team_stats_by_game = {}

        for game_id in game_ids:
            # Get all player stats for this game (excluding the player we're analyzing)
            game_player_stats = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game_id,
                    PlayerGameStat.player_id != exclude_player_id,  # Exclude the player
                    PlayerGameStat.minutes_played > 0
                )
            ).all()

            # Aggregate team stats
            team_totals = {
                'field_goals_made': 0,
                'field_goals_attempted': 0,
                'three_pointers_made': 0,
                'free_throws_made': 0,
                'free_throws_attempted': 0,
                'offensive_rebounds': 0,
                'defensive_rebounds': 0,
                'assists': 0,
                'turnovers': 0,
                'opponent_rebounds': 0  # This will need to be estimated
            }

            for stat in game_player_stats:
                team_totals['field_goals_made'] += stat.field_goals_made or 0
                team_totals['field_goals_attempted'] += stat.field_goals_attempted or 0
                team_totals['three_pointers_made'] += stat.three_pointers_made or 0
                team_totals['free_throws_made'] += stat.free_throws_made or 0
                team_totals['free_throws_attempted'] += stat.free_throws_attempted or 0
                team_totals['offensive_rebounds'] += stat.offensive_rebounds or 0
                team_totals['defensive_rebounds'] += stat.defensive_rebounds or 0
                team_totals['assists'] += stat.assists or 0
                team_totals['turnovers'] += stat.turnovers or 0

            team_stats_by_game[game_id] = team_totals

        return team_stats_by_game

    def _aggregate_player_stats(self, player_stats: List[PlayerGameStat], team_stats: Dict[int, Dict[str, float]]) -> Dict[str, float]:
        """Aggregate player and team statistics."""
        totals = {
            'points': 0, 'fgm': 0, 'fga': 0, 'tpm': 0, 'tpa': 0, 'ftm': 0, 'fta': 0,
            'trb': 0, 'orb': 0, 'drb': 0, 'ast': 0, 'stl': 0, 'blk': 0, 'tov': 0,
            'minutes': 0,
            'team_fgm': 0, 'team_trb': 0, 'team_minutes': 0, 'team_possessions': 0,
            'opp_trb': 0
        }

        # Aggregate player stats
        for stat in player_stats:
            totals['points'] += stat.points or 0
            totals['fgm'] += stat.field_goals_made or 0
            totals['fga'] += stat.field_goals_attempted or 0
            totals['tpm'] += stat.three_pointers_made or 0
            totals['tpa'] += stat.three_pointers_attempted or 0
            totals['ftm'] += stat.free_throws_made or 0
            totals['fta'] += stat.free_throws_attempted or 0
            totals['trb'] += (stat.offensive_rebounds or 0) + (stat.defensive_rebounds or 0)
            totals['orb'] += stat.offensive_rebounds or 0
            totals['drb'] += stat.defensive_rebounds or 0
            totals['ast'] += stat.assists or 0
            totals['stl'] += stat.steals or 0
            totals['blk'] += stat.blocks or 0
            totals['tov'] += stat.turnovers or 0
            totals['minutes'] += stat.minutes_played or 0

        # Aggregate team stats for player's games
        for stat in player_stats:
            if stat.game_id in team_stats:
                game_team_stat = team_stats[stat.game_id]
                totals['team_fgm'] += game_team_stat['field_goals_made']
                totals['team_trb'] += game_team_stat['offensive_rebounds'] + game_team_stat['defensive_rebounds']
                totals['team_minutes'] += 48 * 5  # Assume 5 players * 48 minutes

                # Estimate possessions: FGA + 0.44*FTA - ORB + TOV
                team_poss = game_team_stat['field_goals_attempted'] + \
                           (0.44 * game_team_stat['free_throws_attempted']) - \
                           game_team_stat['offensive_rebounds'] + \
                           game_team_stat['turnovers']
                totals['team_possessions'] += team_poss

        return totals

    def calculate_team_advanced_stats(
        self,
        team_id: int,
        season_id: Optional[int] = None,
        last_n_games: Optional[int] = None
    ) -> Dict[str, float]:
        """
        Calculate advanced statistics for a team.

        Args:
            team_id: Team to analyze
            season_id: Season to analyze
            last_n_games: Limit to last N games

        Returns:
            Dict of team advanced statistics
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return {}
            season_id = season.season_id

        # Get team game stats
        query = self.db.query(TeamGameStat).join(Game).filter(
            and_(
                TeamGameStat.team_id == team_id,
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        )

        if last_n_games:
            query = query.order_by(desc(Game.game_date)).limit(last_n_games)

        team_stats = query.all()

        if not team_stats:
            return {}

        # Aggregate team statistics
        totals = {
            'points': 0, 'fgm': 0, 'fga': 0, 'tpm': 0, 'ftm': 0, 'fta': 0,
            'trb': 0, 'orb': 0, 'drb': 0, 'ast': 0, 'stl': 0, 'blk': 0, 'tov': 0,
            'games': len(team_stats),
            'possessions': 0
        }

        for stat in team_stats:
            totals['points'] += stat.points or 0
            totals['fgm'] += stat.field_goals_made or 0
            totals['fga'] += stat.field_goals_attempted or 0
            totals['tpm'] += stat.three_pointers_made or 0
            totals['ftm'] += stat.free_throws_made or 0
            totals['fta'] += stat.free_throws_attempted or 0
            totals['trb'] += (stat.offensive_rebounds or 0) + (stat.defensive_rebounds or 0)
            totals['orb'] += stat.offensive_rebounds or 0
            totals['drb'] += stat.defensive_rebounds or 0
            totals['ast'] += stat.assists or 0
            totals['stl'] += stat.steals or 0
            totals['blk'] += stat.blocks or 0
            totals['tov'] += stat.turnovers or 0

            # Calculate possessions per game
            poss = (stat.field_goals_attempted or 0) + \
                   (0.44 * (stat.free_throws_attempted or 0)) - \
                   (stat.offensive_rebounds or 0) + \
                   (stat.turnovers or 0)
            totals['possessions'] += poss

        # Calculate per-game averages
        games = totals['games']
        stats = {}

        if games > 0:
            stats['ppg'] = round(totals['points'] / games, 1)
            stats['fg_percent'] = round((totals['fgm'] / totals['fga']) * 100, 1) if totals['fga'] > 0 else 0
            stats['three_percent'] = round((totals['tpm'] / totals['tpa']) * 100, 1) if totals['tpa'] > 0 else 0
            stats['ft_percent'] = round((totals['ftm'] / totals['fta']) * 100, 1) if totals['fta'] > 0 else 0
            stats['rpg'] = round(totals['trb'] / games, 1)
            stats['apg'] = round(totals['ast'] / games, 1)
            stats['spg'] = round(totals['stl'] / games, 1)
            stats['bpg'] = round(totals['blk'] / games, 1)
            stats['tpg'] = round(totals['tov'] / games, 1)
            stats['pace'] = round(totals['possessions'] / games, 1)

            # Effective Field Goal %
            if totals['fga'] > 0:
                stats['efg_percent'] = round(((totals['fgm'] + 0.5 * totals['tpm']) / totals['fga']) * 100, 1)

            # True Shooting %
            ts_points = totals['points']
            ts_attempts = totals['fga'] + (0.44 * totals['fta'])
            if ts_attempts > 0:
                stats['ts_percent'] = round((ts_points / (2 * ts_attempts)) * 100, 1)

        return stats

    def get_advanced_performance_multiplier(
        self,
        player_id: int,
        stat_type: str,
        season_id: Optional[int] = None,
        recent_games: int = 10
    ) -> float:
        """
        Calculate performance multiplier based on advanced analytics.

        Args:
            player_id: Player to analyze
            stat_type: Target stat type
            season_id: Season for analysis
            recent_games: Number of recent games to analyze

        Returns:
            Performance multiplier based on advanced metrics
        """
        # Get advanced stats for recent games
        recent_stats = self.calculate_player_advanced_stats(
            player_id, season_id, last_n_games=recent_games
        )

        if not recent_stats:
            return 1.0

        multiplier = 1.0

        # Apply different advanced metrics based on stat type
        if stat_type == 'points':
            # Points: Use TS%, USG%, and PER
            if 'ts_percent' in recent_stats:
                ts_percent = recent_stats['ts_percent']
                # Above 60% TS% = boost, below 50% = penalty
                if ts_percent >= 60:
                    multiplier *= 1.08
                elif ts_percent <= 50:
                    multiplier *= 0.92

            if 'usg_percent' in recent_stats:
                usg_percent = recent_stats['usg_percent']
                # High usage players are more consistent
                if usg_percent >= 25:
                    multiplier *= 1.03

            if 'per' in recent_stats:
                per = recent_stats['per']
                # PER above 20 = excellent, below 10 = poor
                if per >= 20:
                    multiplier *= 1.05
                elif per <= 10:
                    multiplier *= 0.95

        elif stat_type == 'assists':
            # Assists: Use AST% and PER
            if 'ast_percent' in recent_stats:
                ast_percent = recent_stats['ast_percent']
                # High assist % = good facilitator
                if ast_percent >= 25:
                    multiplier *= 1.06
                elif ast_percent <= 10:
                    multiplier *= 0.94

            if 'per' in recent_stats:
                per = recent_stats['per']
                if per >= 18:
                    multiplier *= 1.04

        elif stat_type == 'rebounds':
            # Rebounds: Use REB% and overall rebounding ability
            if 'reb_percent' in recent_stats:
                reb_percent = recent_stats['reb_percent']
                # High rebound % = good rebounder
                if reb_percent >= 18:
                    multiplier *= 1.07
                elif reb_percent <= 8:
                    multiplier *= 0.93

        elif stat_type == 'three_pointers_made':
            # Three pointers: Use eFG% and 3-point volume
            if 'efg_percent' in recent_stats:
                efg_percent = recent_stats['efg_percent']
                # Good 3-point shooting = boost for 3PM
                if efg_percent >= 55:
                    multiplier *= 1.05
                elif efg_percent <= 45:
                    multiplier *= 0.95

        return max(0.85, min(1.20, multiplier))  # Clamp to reasonable range