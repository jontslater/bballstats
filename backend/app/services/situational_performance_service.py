"""
Situational Performance Service

Analyzes how players perform in different game situations and contexts.
Includes clutch performance, blowout effects, pace context, and more.
"""

from sqlalchemy import and_, func, desc, case
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Tuple
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
# Team stats calculated from player game stats
from datetime import timedelta
import statistics


class SituationalPerformanceService:
    """Analyze player performance in different situational contexts."""

    def __init__(self, db: Session):
        self.db = db

    def calculate_situational_performance(
        self,
        player_id: int,
        stat_type: str,
        season_id: Optional[int] = None,
        min_games: int = 10
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate player performance across different situational contexts.

        Args:
            player_id: Player to analyze
            stat_type: Stat type to analyze
            season_id: Season for analysis
            min_games: Minimum games required for analysis

        Returns:
            Dict of situational contexts with performance data
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return {}
            season_id = season.season_id

        # Get all games with detailed context
        games_with_context = self._get_games_with_situational_context(player_id, season_id)

        if len(games_with_context) < min_games:
            return {}

        situational_stats = {
            'clutch': {'values': [], 'games': 0},  # Last 5 min, close games
            'blowout_winning': {'values': [], 'games': 0},  # Big leads
            'blowout_losing': {'values': [], 'games': 0},  # Big deficits
            'competitive': {'values': [], 'games': 0},  # Close games
            'fast_pace': {'values': [], 'games': 0},  # High tempo games
            'slow_pace': {'values': [], 'games': 0},  # Low tempo games
            'back_to_back': {'values': [], 'games': 0},  # B2B games
            'rested': {'values': [], 'games': 0},  # After rest days
            'home_win': {'values': [], 'games': 0},  # Home wins
            'away_win': {'values': [], 'games': 0},  # Away wins
            'early_season': {'values': [], 'games': 0},  # First 20 games
            'late_season': {'values': [], 'games': 0}  # Last 20 games
        }

        total_games = len(games_with_context)

        for game_data in games_with_context:
            stat_value = self._extract_stat_value(game_data['stats'], stat_type)
            context = game_data['context']

            # Categorize by situational contexts
            self._categorize_situational_performance(
                stat_value, context, situational_stats, total_games
            )

    def _calculate_game_team_stats(self, game_id: int, team_id: int, exclude_player_id: int) -> Dict[str, float]:
        """
        Calculate team stats for a specific game from player stats.
        """
        game_player_stats = self.db.query(PlayerGameStat).filter(
            and_(
                PlayerGameStat.game_id == game_id,
                PlayerGameStat.team_id == team_id,
                PlayerGameStat.player_id != exclude_player_id,
                PlayerGameStat.minutes_played > 0
            )
        ).all()

        team_totals = {
            'points': 0,
            'field_goals_attempted': 0,
            'free_throws_attempted': 0,
            'offensive_rebounds': 0,
            'turnovers': 0
        }

        for stat in game_player_stats:
            team_totals['points'] += stat.points or 0
            team_totals['field_goals_attempted'] += stat.field_goals_attempted or 0
            team_totals['free_throws_attempted'] += stat.free_throws_attempted or 0
            team_totals['offensive_rebounds'] += stat.offensive_rebounds or 0
            team_totals['turnovers'] += stat.turnovers or 0

        return team_totals

        # Calculate averages and performance ratios
        results = {}
        overall_avg = sum(s['_extract_stat_value'](s['stats'], stat_type)
                          for s in games_with_context) / len(games_with_context)

        for situation, data in situational_stats.items():
            if data['games'] >= max(3, min_games // 4):  # Require minimum games per situation
                situation_avg = sum(data['values']) / len(data['values']) if data['values'] else 0
                performance_ratio = situation_avg / overall_avg if overall_avg > 0 else 1.0

                results[situation] = {
                    'average': round(situation_avg, 2),
                    'games': data['games'],
                    'performance_ratio': round(performance_ratio, 3),
                    'vs_overall': round(((performance_ratio - 1.0) * 100), 1)  # % difference
                }

        return results

    def _get_games_with_situational_context(self, player_id: int, season_id: int) -> List[Dict]:
        """
        Get all games for a player with situational context analysis.
        """
        # Get player games with team stats calculated from player stats
        player_games = self.db.query(
            PlayerGameStat, Game
        ).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).order_by(Game.game_date).all()

        # Calculate team stats for each game
        games_data = []
        for player_stat, game in player_games:
            team_stats = self._calculate_game_team_stats(game.game_id, player_stat.team_id, player_id)
            games_data.append((player_stat, game, team_stats))

        games_with_context = []

        for player_stat, game, team_stat in games_data:
            context = self._analyze_game_context(player_stat, game, team_stat)
            games_with_context.append({
                'stats': player_stat,
                'game': game,
                'context': context
            })

        return games_with_context

    def _analyze_game_context(self, player_stat: PlayerGameStat, game: Game, team_stats: Dict[str, float]) -> Dict[str, any]:
        """
        Analyze the situational context of a specific game.
        """
        context = {}

        # Determine if player is home or away
        is_home = (player_stat.team_id == game.home_team_id)
        context['is_home'] = is_home

        # Calculate score differential at end of game
        if is_home:
            final_margin = team_stats['points'] - (game.home_score or 0)
        else:
            final_margin = team_stats['points'] - (game.away_score or 0)
        context['final_margin'] = final_margin
        context['is_win'] = final_margin > 0

        # Clutch situation (last 5 minutes of close games)
        score_diff = abs((game.home_score or 0) - (game.away_score or 0)) if game.home_score is not None and game.away_score is not None else 0
        context['is_clutch'] = score_diff <= 5  # Within 5 points
        context['is_blowout'] = score_diff >= 15  # 15+ point differential

        # Pace context (possessions per game)
        possessions = self._calculate_game_possessions(team_stats)
        context['pace'] = possessions
        context['is_fast_pace'] = possessions >= 105  # Above league average
        context['is_slow_pace'] = possessions <= 95   # Below league average

        # Back-to-back analysis
        context['is_back_to_back'] = self._is_back_to_back_game(player_stat.player_id, game)

        # Rest days analysis
        context['rest_days'] = self._calculate_rest_days(player_stat.player_id, game)

        # Season progression
        context['season_progress'] = self._calculate_season_progress(game, player_stat.player_id)

        return context

    def _calculate_game_possessions(self, team_stats: Dict[str, float]) -> float:
        """
        Calculate possessions for a game.
        Formula: FGA + 0.44*FTA - ORB + TOV
        """
        fga = team_stats['field_goals_attempted']
        fta = team_stats['free_throws_attempted']
        orb = team_stats['offensive_rebounds']
        tov = team_stats['turnovers']

        return fga + (0.44 * fta) - orb + tov

    def _is_back_to_back_game(self, player_id: int, current_game: Game) -> bool:
        """
        Determine if this is a back-to-back game for the player.
        """
        prev_game = self.db.query(Game).join(PlayerGameStat).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.game_date < current_game.game_date,
                Game.game_status == 'finished'
            )
        ).order_by(desc(Game.game_date)).first()

        if not prev_game:
            return False

        # Check if games are on consecutive days
        days_diff = (current_game.game_date - prev_game.game_date).days
        return days_diff == 1

    def _calculate_rest_days(self, player_id: int, current_game: Game) -> int:
        """
        Calculate rest days since last game.
        """
        prev_game = self.db.query(Game).join(PlayerGameStat).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.game_date < current_game.game_date,
                Game.game_status == 'finished'
            )
        ).order_by(desc(Game.game_date)).first()

        if not prev_game:
            return 7  # Assume well-rested for first game

        days_diff = (current_game.game_date - prev_game.game_date).days
        return max(0, days_diff - 1)  # Subtract 1 for consecutive days

    def _calculate_season_progress(self, game: Game, player_id: int) -> str:
        """
        Determine season progression (early/late season).
        """
        # Count total games played by player this season
        total_games = self.db.query(PlayerGameStat).join(Game).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == game.season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).count()

        if total_games <= 20:
            return 'early'
        elif total_games >= 60:  # Typical NBA season has ~82 games
            return 'late'
        else:
            return 'mid'

    def _categorize_situational_performance(self, stat_value: float, context: Dict, situational_stats: Dict, total_games: int):
        """
        Categorize performance into situational buckets.
        """
        # Clutch situations
        if context.get('is_clutch', False):
            situational_stats['clutch']['values'].append(stat_value)
            situational_stats['clutch']['games'] += 1

        # Blowout situations
        if context.get('is_blowout', False):
            if context.get('final_margin', 0) > 0:
                situational_stats['blowout_winning']['values'].append(stat_value)
                situational_stats['blowout_winning']['games'] += 1
            else:
                situational_stats['blowout_losing']['values'].append(stat_value)
                situational_stats['blowout_losing']['games'] += 1
        else:
            situational_stats['competitive']['values'].append(stat_value)
            situational_stats['competitive']['games'] += 1

        # Pace context
        if context.get('is_fast_pace', False):
            situational_stats['fast_pace']['values'].append(stat_value)
            situational_stats['fast_pace']['games'] += 1
        elif context.get('is_slow_pace', False):
            situational_stats['slow_pace']['values'].append(stat_value)
            situational_stats['slow_pace']['games'] += 1

        # Back-to-back
        if context.get('is_back_to_back', False):
            situational_stats['back_to_back']['values'].append(stat_value)
            situational_stats['back_to_back']['games'] += 1
        else:
            situational_stats['rested']['values'].append(stat_value)
            situational_stats['rested']['games'] += 1

        # Home/away splits
        if context.get('is_home', False) and context.get('is_win', False):
            situational_stats['home_win']['values'].append(stat_value)
            situational_stats['home_win']['games'] += 1
        elif not context.get('is_home', False) and context.get('is_win', False):
            situational_stats['away_win']['values'].append(stat_value)
            situational_stats['away_win']['games'] += 1

        # Season progression
        season_progress = context.get('season_progress', 'mid')
        if season_progress == 'early':
            situational_stats['early_season']['values'].append(stat_value)
            situational_stats['early_season']['games'] += 1
        elif season_progress == 'late':
            situational_stats['late_season']['values'].append(stat_value)
            situational_stats['late_season']['games'] += 1

    def _extract_stat_value(self, player_stat: PlayerGameStat, stat_type: str) -> float:
        """
        Extract the appropriate stat value from player stats.
        """
        if stat_type == 'points':
            return player_stat.points or 0
        elif stat_type == 'rebounds':
            return (player_stat.offensive_rebounds or 0) + (player_stat.defensive_rebounds or 0)
        elif stat_type == 'assists':
            return player_stat.assists or 0
        elif stat_type == 'three_pointers_made':
            return player_stat.three_pointers_made or 0
        else:
            return 0

    def get_situational_performance_multiplier(
        self,
        player_id: int,
        stat_type: str,
        game_context: Dict,
        season_id: Optional[int] = None
    ) -> float:
        """
        Calculate performance multiplier based on current game situation.

        Args:
            player_id: Player to analyze
            stat_type: Target stat type
            game_context: Current game situational context
            season_id: Season for historical analysis

        Returns:
            Performance multiplier (0.9 to 1.1)
        """
        situational_performance = self.calculate_situational_performance(
            player_id, stat_type, season_id, min_games=15
        )

        if not situational_performance:
            return 1.0

        multiplier = 1.0
        applied_adjustments = 0

        # Apply situational adjustments
        context_mappings = {
            'is_clutch': 'clutch',
            'is_fast_pace': 'fast_pace',
            'is_slow_pace': 'slow_pace',
            'is_back_to_back': 'back_to_back'
        }

        # Check direct situational contexts
        for context_key, situation_key in context_mappings.items():
            if game_context.get(context_key, False) and situation_key in situational_performance:
                perf_ratio = situational_performance[situation_key]['performance_ratio']
                # Apply moderate adjustment based on historical performance
                adjustment = 1.0 + ((perf_ratio - 1.0) * 0.3)  # 30% weight
                multiplier *= adjustment
                applied_adjustments += 1

        # Check rest days impact
        rest_days = game_context.get('rest_days', 1)
        if rest_days >= 2 and 'rested' in situational_performance:
            perf_ratio = situational_performance['rested']['performance_ratio']
            adjustment = 1.0 + ((perf_ratio - 1.0) * 0.2)
            multiplier *= adjustment
            applied_adjustments += 1

        # Blowout context
        is_blowout = game_context.get('is_blowout', False)
        final_margin = game_context.get('final_margin', 0)

        if is_blowout:
            if final_margin > 0 and 'blowout_winning' in situational_performance:
                perf_ratio = situational_performance['blowout_winning']['performance_ratio']
                adjustment = 1.0 + ((perf_ratio - 1.0) * 0.25)
                multiplier *= adjustment
            elif final_margin < 0 and 'blowout_losing' in situational_performance:
                perf_ratio = situational_performance['blowout_losing']['performance_ratio']
                adjustment = 1.0 + ((perf_ratio - 1.0) * 0.25)
                multiplier *= adjustment
            applied_adjustments += 1

        # If multiple adjustments applied, take geometric mean
        if applied_adjustments > 1:
            multiplier = multiplier ** (1.0 / applied_adjustments)

        return max(0.85, min(1.15, multiplier))  # Clamp to reasonable range