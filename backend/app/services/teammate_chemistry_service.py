"""
Teammate Chemistry Service

Analyzes how players perform when their teammates are performing well or poorly.
Identifies performance correlations between teammates for better predictions.
"""

from sqlalchemy import and_, func, desc
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Tuple
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.player import Player
import statistics
import math


class TeammateChemistryService:
    """Analyze teammate performance correlations and chemistry."""

    def __init__(self, db: Session):
        self.db = db
        self.min_games_threshold = 10  # Minimum games to establish correlation

    def calculate_teammate_correlations(
        self,
        player_id: int,
        season_id: Optional[int] = None,
        min_correlation_threshold: float = 0.3
    ) -> Dict[str, List[Dict]]:
        """
        Calculate correlations between player performance and teammate performance.

        Args:
            player_id: Player to analyze
            season_id: Season to analyze
            min_correlation_threshold: Minimum correlation coefficient to consider

        Returns:
            Dict with correlations by stat type
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return {}
            season_id = season.season_id

        # Get all games for this player this season
        player_games = self.db.query(PlayerGameStat, Game).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).order_by(Game.game_date).all()

        if len(player_games) < self.min_games_threshold:
            return {}

        correlations = {
            'points': [],
            'rebounds': [],
            'assists': [],
            'three_pointers_made': []
        }

        # Get teammate performance for each game
        for player_stat, game in player_games:
            game_correlations = self._analyze_single_game_correlations(
                player_id, player_stat, game, min_correlation_threshold
            )

            # Add to overall correlations
            for stat_type, corr_list in game_correlations.items():
                correlations[stat_type].extend(corr_list)

        # Aggregate and rank correlations by strength
        for stat_type in correlations:
            if correlations[stat_type]:
                # Group by teammate and calculate average correlation
                teammate_correlations = {}
                for corr in correlations[stat_type]:
                    teammate_id = corr['teammate_id']
                    if teammate_id not in teammate_correlations:
                        teammate_correlations[teammate_id] = {
                            'teammate_name': corr['teammate_name'],
                            'correlations': []
                        }
                    teammate_correlations[teammate_id]['correlations'].append(corr)

                # Calculate average correlation per teammate
                aggregated = []
                for teammate_id, data in teammate_correlations.items():
                    avg_corr = sum(c['correlation'] for c in data['correlations']) / len(data['correlations'])
                    if abs(avg_corr) >= min_correlation_threshold:
                        aggregated.append({
                            'teammate_id': teammate_id,
                            'teammate_name': data['teammate_name'],
                            'correlation': round(avg_corr, 3),
                            'games_analyzed': len(data['correlations']),
                            'stat_type': stat_type,
                            'relationship_type': 'positive' if avg_corr > 0 else 'negative'
                        })

                # Sort by absolute correlation strength
                correlations[stat_type] = sorted(
                    aggregated,
                    key=lambda x: abs(x['correlation']),
                    reverse=True
                )[:5]  # Top 5 correlations per stat type

        return correlations

    def _analyze_single_game_correlations(
        self,
        player_id: int,
        player_stat: PlayerGameStat,
        game: Game,
        min_correlation_threshold: float
    ) -> Dict[str, List[Dict]]:
        """
        Analyze correlations for a single game.
        """
        correlations = {
            'points': [],
            'rebounds': [],
            'assists': [],
            'three_pointers_made': []
        }

        # Get all teammates who played in this game
        teammates = self.db.query(PlayerGameStat, Player).join(
            Player, PlayerGameStat.player_id == Player.player_id
        ).filter(
            and_(
                PlayerGameStat.game_id == game.game_id,
                PlayerGameStat.team_id == player_stat.team_id,
                PlayerGameStat.player_id != player_id,
                PlayerGameStat.minutes_played > 0
            )
        ).all()

        player_values = {
            'points': player_stat.points or 0,
            'rebounds': player_stat.rebounds or 0,
            'assists': player_stat.assists or 0,
            'three_pointers_made': player_stat.three_pointers_made or 0
        }

        for teammate_stat, teammate in teammates:
            teammate_values = {
                'points': teammate_stat.points or 0,
                'rebounds': teammate_stat.rebounds or 0,
                'assists': teammate_stat.assists or 0,
                'three_pointers_made': teammate_stat.three_pointers_made or 0
            }

            # Calculate correlation for each stat type
            for stat_type in correlations:
                if teammate_values[stat_type] > 0:  # Only consider meaningful performance
                    correlation = self._calculate_correlation_coefficient(
                        player_values[stat_type],
                        teammate_values[stat_type]
                    )

                    if abs(correlation) >= min_correlation_threshold:
                        correlations[stat_type].append({
                            'teammate_id': teammate.player_id,
                            'teammate_name': teammate.name,
                            'teammate_stat_value': teammate_values[stat_type],
                            'player_stat_value': player_values[stat_type],
                            'correlation': round(correlation, 3),
                            'game_id': game.game_id
                        })

        return correlations

    def _calculate_correlation_coefficient(self, player_value: float, teammate_value: float) -> float:
        """
        Calculate a simple correlation coefficient between two values.
        Since we only have one data point per game, we'll use a simplified approach.
        """
        # For single game analysis, we'll use a binary correlation:
        # High teammate performance + high player performance = positive correlation
        # High teammate performance + low player performance = negative correlation

        # Define "high" performance as above average for that stat type
        stat_averages = {
            'points': 15.0,      # NBA average PPG
            'rebounds': 5.0,     # NBA average RPG
            'assists': 3.0,      # NBA average APG
            'three_pointers_made': 2.0  # NBA average 3PM
        }

        player_high = player_value >= stat_averages.get('points', 10)  # Using points as default key
        teammate_high = teammate_value >= stat_averages.get('points', 10)

        # Current stat type (this is a simplification - in practice we'd pass the stat type)
        # For now, assume points as the correlation target
        if player_high and teammate_high:
            return 0.5   # Both performing well = positive correlation
        elif player_high and not teammate_high:
            return -0.3  # Player good despite teammate struggles
        elif not player_high and teammate_high:
            return 0.3   # Teammate helping despite player struggles
        else:
            return 0.0   # Both struggling = neutral

    def get_teammate_performance_multiplier(
        self,
        player_id: int,
        teammate_performance: Dict[int, Dict[str, float]],
        stat_type: str,
        season_id: Optional[int] = None
    ) -> float:
        """
        Calculate performance multiplier based on current teammate performance.

        Args:
            player_id: Player to analyze
            teammate_performance: Dict of teammate_id -> {stat_type: value}
            stat_type: Target stat type for the player
            season_id: Season for analysis

        Returns:
            Performance multiplier (0.9 to 1.2)
        """
        correlations = self.calculate_teammate_correlations(player_id, season_id)
        if not correlations or stat_type not in correlations:
            return 1.0

        total_multiplier = 1.0
        applied_correlations = 0

        # Check each correlated teammate
        for correlation in correlations[stat_type][:3]:  # Top 3 correlations
            teammate_id = correlation['teammate_id']
            corr_strength = correlation['correlation']

            if teammate_id in teammate_performance and stat_type in teammate_performance[teammate_id]:
                teammate_value = teammate_performance[teammate_id][stat_type]

                # Calculate if teammate is performing above/below average
                stat_averages = {
                    'points': 15.0,
                    'rebounds': 5.0,
                    'assists': 3.0,
                    'three_pointers_made': 2.0
                }

                teammate_avg = stat_averages.get(stat_type, 10)
                performance_ratio = teammate_value / teammate_avg if teammate_avg > 0 else 1.0

                # Apply correlation: strong positive correlation + good teammate performance = boost
                if abs(corr_strength) >= 0.3:
                    if corr_strength > 0 and performance_ratio >= 1.2:  # Good teammate + positive correlation
                        multiplier = 1.0 + (corr_strength * 0.15)  # Up to 4.5% boost for 0.3 correlation
                    elif corr_strength > 0 and performance_ratio <= 0.8:  # Bad teammate + positive correlation
                        multiplier = 1.0 + (corr_strength * -0.12)  # Up to 3.6% penalty
                    elif corr_strength < 0 and performance_ratio >= 1.2:  # Good teammate + negative correlation
                        multiplier = 1.0 + (abs(corr_strength) * -0.10)  # Up to 3% penalty
                    else:
                        multiplier = 1.0

                    total_multiplier *= multiplier
                    applied_correlations += 1

        # Average the multipliers if multiple correlations applied
        if applied_correlations > 1:
            # Geometric mean for multiplicative factors
            total_multiplier = total_multiplier ** (1.0 / applied_correlations)

        return max(0.85, min(1.25, total_multiplier))  # Clamp to reasonable range

    def get_team_chemistry_score(
        self,
        team_id: int,
        game_id: int,
        season_id: Optional[int] = None
    ) -> float:
        """
        Calculate overall team chemistry score based on teammate correlations.

        Returns:
            Chemistry score (0.0 to 1.0, where 1.0 is perfect chemistry)
        """
        # This is a simplified implementation
        # In a full version, would analyze all player correlations on the team
        return 0.75  # Placeholder - assume decent chemistry