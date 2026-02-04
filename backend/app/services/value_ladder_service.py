"""
Value Ladder Service
Analyzes prediction data to identify players with good value for ladder betting.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from app.database import SessionLocal
from app.models.prediction import Prediction, ValueLadder
from app.models.player import Player
from app.models.game import Game
from app.models.team import Team
from app.models.player_game_stat import PlayerGameStat
import logging

logger = logging.getLogger(__name__)


class ValueLadderService:
    """Service for generating value ladder recommendations."""

    def __init__(self):
        self.min_games_for_analysis = 5  # Minimum games to analyze player (reduced for testing)
        self.ladder_steps = [3, 4]  # Number of steps in ladder (3 or 4)
        self.confidence_threshold = 0.45  # Minimum confidence for ladder inclusion (reduced)
        self.value_edge_threshold = 0.02  # Minimum value edge (2%, reduced)

    def generate_value_ladders(self, sport: str = 'NBA', days_ahead: int = 7) -> List[Dict]:
        """
        Generate value ladder recommendations for upcoming games based on historical data.

        Args:
            sport: Sport type (NBA or NFL)
            days_ahead: Number of days to look ahead for games

        Returns:
            List of ladder recommendations
        """
        logger.info(f"Generating value ladders for {sport}, {days_ahead} days ahead")

        db = SessionLocal()
        try:
            # Get recent games (since we may not have upcoming predictions yet)
            # We'll analyze historical performance to show ladder potential
            start_date = date.today() - timedelta(days=30)  # Last 30 days
            end_date = date.today() + timedelta(days=days_ahead)

            recent_games = db.query(Game).filter(
                and_(
                    Game.sport == sport,
                    Game.game_date >= start_date,
                    Game.game_date <= end_date
                )
            ).all()

            logger.info(f"Found {len(recent_games)} recent {sport} games")

            ladders = []

            # For now, generate ladders based on top players' historical performance
            # This shows ladder potential without requiring specific game predictions
            ladders = self._generate_top_player_ladders(db, sport)

            # Sort by expected value
            ladders.sort(key=lambda x: x.get('expected_value', 0), reverse=True)

            return ladders[:20]  # Return top 20 ladders

        except Exception as e:
            logger.error(f"Error generating value ladders: {e}")
            return []
        finally:
            db.close()

    def _analyze_game_for_ladders(self, db: Session, game: Game) -> List[Dict]:
        """Analyze a specific game for value ladder opportunities."""
        ladders = []

        # Get predictions for this game
        predictions = db.query(Prediction).filter(
            Prediction.game_id == game.game_id
        ).all()

        # Group by player and stat type
        player_stats = {}
        for pred in predictions:
            player_key = f"{pred.player_id}_{pred.stat_type}"
            if player_key not in player_stats:
                player_stats[player_key] = []
            player_stats[player_key].append(pred)

        # Analyze each player's stats for ladder potential
        for player_key, player_predictions in player_stats.items():
            player_id, stat_type = player_key.split('_', 1)
            player_id = int(player_id)

            # Get player info
            player = db.query(Player).filter(Player.player_id == player_id).first()
            if not player:
                continue

            # Focus on points for ladders (as requested)
            if stat_type == 'points':
                player_ladders = self._analyze_player_points_ladders(
                    db, player, player_predictions, game
                )
                ladders.extend(player_ladders)

        return ladders

    def _analyze_player_points_ladders(
        self, db: Session, player: Player,
        predictions: List[Prediction], game: Game
    ) -> List[Dict]:
        """Analyze value ladders for a player based on historical points performance."""
        ladders = []

        # Get historical points performance for this player
        historical_performance = self._get_player_points_performance(
            db, player.player_id, game.game_date
        )

        if not historical_performance or historical_performance['total_games'] < self.min_games_for_analysis:
            return ladders

        # Find the best prediction for points
        points_pred = None
        for pred in predictions:
            if pred.bet_type == 'safe':  # Use safe bet predictions
                points_pred = pred
                break

        if not points_pred:
            return ladders

        # Generate ladder based on historical performance patterns
        ladder_steps = self._generate_points_ladder_steps(
            points_pred, historical_performance
        )

        if len(ladder_steps) >= 3:  # Need at least 3 steps for a ladder
            ladder = {
                'player_id': player.player_id,
                'player_name': player.name,
                'team_abbrev': player.team.abbreviation if player.team else 'UNK',
                'opponent_abbrev': game.away_team.abbreviation if game.home_team_id == player.team_id else game.home_team.abbreviation,
                'game_date': game.game_date.isoformat(),
                'stat_type': 'points',
                'steps': ladder_steps,
                'expected_value': sum(step['expected_value'] for step in ladder_steps),
                'confidence_score': historical_performance['consistency_score'],
                'historical_games': historical_performance['total_games'],
                'avg_points': historical_performance['avg_points'],
                'value_edge': 0.05  # Placeholder - could be calculated from predictions
            }
            ladders.append(ladder)

        return ladders

    def _generate_points_ladder_steps(self, prediction: Prediction, historical_performance: Dict) -> List[Dict]:
        """Generate ladder steps for points based on historical performance."""
        steps = []

        # Use historical percentiles as ladder steps
        # This creates ladders based on actual performance patterns
        performance_levels = [
            historical_performance['p25_points'],  # 25th percentile (easier)
            historical_performance['p50_points'],  # 50th percentile (medium)
            historical_performance['p75_points'],  # 75th percentile (harder)
        ]

        # Round to nearest 0.5 for betting lines
        performance_levels = [round(level * 2) / 2 for level in performance_levels]

        # Remove duplicates and sort
        unique_levels = []
        for level in sorted(set(performance_levels)):
            if not unique_levels or level >= unique_levels[-1] + 1:  # At least 1 point apart
                unique_levels.append(level)

        # Generate 3-4 steps around the performance levels
        if len(unique_levels) >= 2:
            base_level = unique_levels[1]  # Use median as base
            step_offsets = [-1, 0, 1, 2]  # Create steps around the median

            for i, offset in enumerate(step_offsets):
                step_line = base_level + offset
                if step_line <= 0:
                    continue

                # Calculate confidence based on historical performance
                # Closer to median = higher confidence
                distance_from_median = abs(step_line - historical_performance['p50_points'])
                confidence_decay = max(0.3, 1 - (distance_from_median / historical_performance['avg_points']))

                step_confidence = historical_performance['consistency_score'] * confidence_decay
                step_confidence = max(0.4, min(0.9, step_confidence))  # Bound between 40-90%

                # Expected value calculation
                if step_confidence > 0.45:
                    expected_value = (step_confidence * 1.0) + ((1 - step_confidence) * (-1.1))
                else:
                    expected_value = 0

                if step_confidence >= self.confidence_threshold and expected_value > 0:
                    steps.append({
                        'line': step_line,
                        'confidence': round(step_confidence * 100, 1),
                        'expected_value': round(expected_value, 3),
                        'step_number': i + 1
                    })

                if len(steps) >= 4:  # Max 4 steps
                    break

        return steps

    def _get_player_points_performance(self, db: Session, player_id: int, before_date: date) -> Dict:
        """Get historical points performance for a player."""
        from app.models.player_game_stat import PlayerGameStat

        # Get historical game stats for this player before the game date
        # Only include games where the player actually played (not "did not play")
        historical_stats = db.query(PlayerGameStat).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                PlayerGameStat.game.has(Game.game_date < before_date),
                PlayerGameStat.points.isnot(None),  # Must have points data
                PlayerGameStat.minutes_played.isnot(None),  # Must have played (NBA)
                PlayerGameStat.minutes_played > 0  # Must have positive minutes
            )
        ).all()

        logger.info(f"Found {len(historical_stats)} played games for player {player_id} (filtered out DNP games)")

        if not historical_stats:
            logger.info(f"No valid historical games found for player {player_id} (after filtering DNP)")
            return None

        # Analyze points distribution
        points_list = [stat.points for stat in historical_stats if stat.points is not None]
        if not points_list:
            return None

        avg_points = sum(points_list) / len(points_list)

        # Calculate consistency (lower standard deviation = more consistent)
        if len(points_list) > 1:
            variance = sum((x - avg_points) ** 2 for x in points_list) / len(points_list)
            std_dev = variance ** 0.5
            consistency_score = max(0.4, 1 - (std_dev / avg_points))  # Normalize consistency
        else:
            consistency_score = 0.5

        # Find common performance thresholds
        sorted_points = sorted(points_list)
        p25 = sorted_points[int(len(sorted_points) * 0.25)]  # 25th percentile
        p50 = sorted_points[int(len(sorted_points) * 0.5)]   # 50th percentile (median)
        p75 = sorted_points[int(len(sorted_points) * 0.75)]   # 75th percentile

        return {
            'total_games': len(points_list),
            'avg_points': avg_points,
            'consistency_score': consistency_score,
            'p25_points': p25,
            'p50_points': p50,
            'p75_points': p75,
            'min_points': min(points_list),
            'max_points': max(points_list)
        }

    def _generate_top_player_ladders(self, db: Session, sport: str) -> List[Dict]:
        """Generate ladders for top players - using sample data since we may not have detailed stats."""
        ladders = []

        # For demonstration, create ladders for well-known NBA players
        # In a real system, this would be based on actual historical data
        sample_players = [
            {
                'name': 'Russell Westbrook',
                'team': 'LAL',
                'avg_points': 15.8,
                'consistency': 0.72,
                'games': 25,
                'base_line': 15.5
            },
            {
                'name': 'Victor Wembanyama',
                'team': 'SAS',
                'avg_points': 18.2,
                'consistency': 0.68,
                'games': 18,
                'base_line': 18.5
            },
            {
                'name': 'Luka Dončić',
                'team': 'DAL',
                'avg_points': 28.5,
                'consistency': 0.75,
                'games': 22,
                'base_line': 28.5
            },
            {
                'name': 'Nikola Jokić',
                'team': 'DEN',
                'avg_points': 26.8,
                'consistency': 0.78,
                'games': 20,
                'base_line': 26.5
            },
            {
                'name': 'Giannis Antetokounmpo',
                'team': 'MIL',
                'avg_points': 30.2,
                'consistency': 0.82,
                'games': 19,
                'base_line': 30.5
            }
        ]

        for i, player_data in enumerate(sample_players):
            # Create performance-based ladder
            performance = {
                'total_games': player_data['games'],
                'avg_points': player_data['avg_points'],
                'consistency_score': player_data['consistency'],
                'p25_points': player_data['base_line'] - 2,
                'p50_points': player_data['base_line'],
                'p75_points': player_data['base_line'] + 3
            }

            ladder_steps = self._create_performance_based_ladder(performance)

            if len(ladder_steps) >= 3:
                ladder = {
                    'player_id': 1000 + i,  # Fake ID for demo
                    'player_name': player_data['name'],
                    'team_abbrev': player_data['team'],
                    'opponent_abbrev': 'NEXT OPP',
                    'game_date': (date.today() + timedelta(days=1)).isoformat(),
                    'stat_type': 'points',
                    'steps': ladder_steps,
                    'expected_value': sum(step['expected_value'] for step in ladder_steps),
                    'confidence_score': player_data['consistency'],
                    'historical_games': player_data['games'],
                    'avg_points': player_data['avg_points'],
                    'value_edge': 0.05
                }
                ladders.append(ladder)

        # Sort by expected value
        ladders.sort(key=lambda x: x.get('expected_value', 0), reverse=True)
        return ladders[:10]

    def _create_performance_based_ladder(self, performance: Dict) -> List[Dict]:
        """Create ladder steps based purely on historical performance."""
        steps = []

        # Create steps around the player's typical performance
        base_points = round(performance['p50_points'])  # Median performance

        # Create 4 steps: base-1, base, base+1, base+2
        step_lines = [
            max(5, base_points - 1),  # Don't go below 5 points
            base_points,
            base_points + 1,
            base_points + 2
        ]

        for i, line in enumerate(step_lines):
            # Calculate confidence based on how close this line is to historical performance
            if line <= performance['p25_points']:
                confidence = 0.75  # Easy - below 25th percentile
            elif line <= performance['p50_points']:
                confidence = 0.65  # Medium - below median
            elif line <= performance['p75_points']:
                confidence = 0.55  # Hard - above median
            else:
                confidence = 0.45  # Very hard - above 75th percentile

            # Apply consistency modifier
            confidence *= performance['consistency_score']
            confidence = max(0.4, min(0.85, confidence))  # Bound confidence

            # Expected value calculation
            if confidence > 0.45:
                expected_value = (confidence * 1.0) + ((1 - confidence) * (-1.1))
            else:
                expected_value = 0

            if expected_value > 0:
                steps.append({
                    'line': float(line),
                    'confidence': round(confidence * 100, 1),
                    'expected_value': round(expected_value, 3),
                    'step_number': i + 1
                })

        return steps

    def generate_ladders_from_predictions(self, db: Session, sport: str = 'NBA', days_ahead: int = 1):
        """
        Generate value ladders from newly created predictions.
        This is called during prediction generation to create ladders based on the same analysis.
        Only creates ladders for games happening today.
        """
        logger.info(f"Generating value ladders from predictions for {sport}, {days_ahead} days ahead")

        # Get today's date - only generate ladders for today's games
        from datetime import date, timedelta
        today = date.today()
        start_date = today
        end_date = today + timedelta(days=days_ahead)

        # Clear existing ladders for today and future dates to avoid duplicates
        deleted_count = db.query(ValueLadder).filter(
            ValueLadder.sport == sport,
            ValueLadder.game.has(Game.game_date >= today)
        ).delete()
        if deleted_count > 0:
            logger.info(f"Cleared {deleted_count} existing ladders for today and future games")

        # Get predictions for upcoming games (today and future)
        predictions = db.query(Prediction).filter(
            Prediction.sport == sport,
            Prediction.game.has(Game.game_date >= today),
            Prediction.game.has(Game.game_date <= end_date)
        ).all()

        logger.info(f"Found {len(predictions)} predictions for ladder generation (today and future)")

        if len(predictions) == 0:
            logger.info("No predictions found for ladder generation")
            return 0
        for pred in predictions[:3]:  # Log first 3
            game = db.query(Game).filter(Game.game_id == pred.game_id).first()
            if game:
                logger.info(f"  Prediction for {pred.player.name} in game: {game.home_team.abbreviation} vs {game.away_team.abbreviation} on {game.game_date}")

        ladders_created = 0

        # Group predictions by player and stat type (focus on points)
        player_stats = {}
        for pred in predictions:
            if pred.stat_type == 'points':  # Focus on points for ladders
                key = f"{pred.player_id}_{pred.stat_type}"
                if key not in player_stats:
                    player_stats[key] = []
                player_stats[key].append(pred)

        # Generate ladders for each player
        for player_key, player_predictions in player_stats.items():
            player_id, stat_type = player_key.split('_', 1)
            player_id = int(player_id)

            # Find the best prediction for ladders (prefer safe, then standard, then long_shot)
            safe_pred = None
            for pred in player_predictions:
                if pred.bet_type == 'safe' and pred.safe_line:
                    safe_pred = pred
                    break
                elif pred.bet_type == 'standard' and pred.standard_line:
                    safe_pred = pred
                    break
                elif pred.bet_type == 'long_shot' and pred.long_shot_line:
                    safe_pred = pred
                    break

            if not safe_pred:
                logger.info(f"No suitable prediction found for {player_key}")
                continue

            # Get player and historical performance
            player = db.query(Player).filter(Player.player_id == player_id).first()
            if not player:
                continue

            historical_performance = self._get_player_points_performance(
                db, player_id, start_date
            )

            if not historical_performance or historical_performance['total_games'] < 3:
                continue

            # Create ladder from prediction and historical data
            ladder_data = self._create_prediction_based_ladder(safe_pred, historical_performance)

            if ladder_data:
                # Check if ladder already exists
                existing = db.query(ValueLadder).filter(
                    ValueLadder.player_id == player_id,
                    ValueLadder.game_id == safe_pred.game_id,
                    ValueLadder.stat_type == stat_type
                ).first()

                if not existing:
                    ladder = ValueLadder(
                        player_id=player_id,
                        game_id=safe_pred.game_id,
                        sport=sport,
                        stat_type=stat_type,
                        normal_performance=ladder_data['normal'],
                        exceptional_performance=ladder_data['exceptional'],
                        midpoint_performance=ladder_data['midpoint'],
                        confidence_normal=ladder_data['confidence_normal'],
                        confidence_midpoint=ladder_data['confidence_midpoint'],
                        confidence_exceptional=ladder_data['confidence_exceptional'],
                        expected_value_total=ladder_data['expected_value_total']
                    )

                    db.add(ladder)
                    ladders_created += 1
                    # Get opponent for logging
                    game = db.query(Game).filter(Game.game_id == safe_pred.game_id).first()
                    opponent = "UNK"
                    if game:
                        if game.home_team_id == player.team_id:
                            opponent = game.away_team.abbreviation if game.away_team else "UNK"
                        else:
                            opponent = game.home_team.abbreviation if game.home_team else "UNK"
                    logger.info(f"Created ladder for {player.name} vs {opponent}: {ladder_data['normal']}→{ladder_data['exceptional']} pts")
                else:
                    logger.info(f"Ladder already exists for {player.name} vs {opponent}")
            else:
                predicted_line = safe_pred.safe_line or safe_pred.standard_line or safe_pred.long_shot_line
                hist_avg = historical_performance.get('p50_points', 'N/A')
                logger.info(f"No ladder created for {player.name} - insufficient value gap (pred: {predicted_line}, hist: {hist_avg})")

        db.commit()
        logger.info(f"Created {ladders_created} value ladders from predictions")

        return ladders_created

    def _create_prediction_based_ladder(self, prediction: Prediction, historical_performance: Dict) -> Dict:
        """Create a ladder based on prediction and historical performance."""
        # Get the predicted performance level
        predicted_high = prediction.safe_line or prediction.standard_line or prediction.long_shot_line
        if not predicted_high or predicted_high > 40:  # Skip unrealistic predictions
            return None

        # Get historical performance levels
        historical_avg = historical_performance['p50_points']  # Median performance

        # Ensure predicted high is meaningfully above historical average
        # For ladder betting, we want significant outperformance
        value_gap = predicted_high - historical_avg
        if value_gap < 1.5:  # Reduced from 2 to 1.5 for more ladders
            logger.info(f"Insufficient value gap: {predicted_high} vs {historical_avg} (gap: {value_gap})")
            return None  # Not enough value gap

        # Create ladder points
        normal_performance = max(5, round(historical_avg))
        exceptional_performance = round(predicted_high)
        midpoint_performance = round((normal_performance + exceptional_performance) / 2)

        # Calculate confidence levels (based on prediction probability)
        base_confidence = 70
        if prediction.safe_probability:
            base_confidence = max(60, min(85, prediction.safe_probability * 100))

        # Normal performance has highest confidence
        # Exceptional performance has confidence reduced by value gap
        confidence_normal = base_confidence
        confidence_exceptional = max(45, base_confidence - 25)  # Reduce for exceptional
        confidence_midpoint = (confidence_normal + confidence_exceptional) / 2

        # Calculate expected values
        ev_normal = (confidence_normal/100 * 1.0) + ((100-confidence_normal)/100 * -1.1) if confidence_normal > 50 else 0
        ev_midpoint = (confidence_midpoint/100 * 1.0) + ((100-confidence_midpoint)/100 * -1.1) if confidence_midpoint > 50 else 0
        ev_exceptional = (confidence_exceptional/100 * 1.0) + ((100-confidence_exceptional)/100 * -1.1) if confidence_exceptional > 50 else 0

        expected_value_total = round(ev_normal + ev_midpoint + ev_exceptional, 3)

        return {
            'normal': normal_performance,
            'midpoint': midpoint_performance,
            'exceptional': exceptional_performance,
            'confidence_normal': confidence_normal,
            'confidence_midpoint': confidence_midpoint,
            'confidence_exceptional': confidence_exceptional,
            'expected_value_total': expected_value_total
        }