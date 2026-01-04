"""
Prediction Evaluator Service

Evaluates predictions after games finish to determine which bets hit.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import Dict, List, Optional
from datetime import date, timedelta
from app.models.prediction import Prediction
from app.models.game import Game
from app.models.player_game_stat import PlayerGameStat
from app.models.player import Player


class PredictionEvaluator:
    """Evaluate predictions against actual game results."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def evaluate_prediction(self, prediction: Prediction) -> Dict[str, any]:
        """
        Evaluate a single prediction against actual results.
        
        Returns:
            Dict with evaluation results
        """
        # Get actual game stat
        stat = self.db.query(PlayerGameStat).filter(
            and_(
                PlayerGameStat.player_id == prediction.player_id,
                PlayerGameStat.game_id == prediction.game_id
            )
        ).first()
        
        if not stat:
            # Player didn't play - mark as void (special status)
            # For predictions, we'll set actual_result to None and mark as void
            # Note: Prediction model doesn't have a 'void' status field, so we'll use a special marker
            # We'll handle void status in the evaluation logic
            prediction.actual_result = None
            # Store void status in a way we can check later
            # For now, we'll mark it as evaluated but with actual_result = None and a special flag
            return {
                'evaluated': True,
                'void': True,
                'reason': 'Player did not play',
                'actual_result': None
            }
        
        # Get actual value based on stat type
        # IMPORTANT: Check for None explicitly, as 0 is a valid stat value
        actual_value = None
        if prediction.stat_type == 'points':
            actual_value = stat.points if stat.points is not None else None
        elif prediction.stat_type == 'rebounds':
            actual_value = stat.rebounds if stat.rebounds is not None else None
        elif prediction.stat_type == 'assists':
            actual_value = stat.assists if stat.assists is not None else None
        elif prediction.stat_type == 'minutes':
            actual_value = stat.minutes_played if stat.minutes_played is not None else None
        elif prediction.stat_type == 'points_rebounds':
            # Combo: points + rebounds
            if stat.points is not None and stat.rebounds is not None:
                actual_value = stat.points + stat.rebounds
        elif prediction.stat_type == 'points_assists':
            # Combo: points + assists
            if stat.points is not None and stat.assists is not None:
                actual_value = stat.points + stat.assists
        elif prediction.stat_type == 'rebounds_assists':
            # Combo: rebounds + assists
            if stat.rebounds is not None and stat.assists is not None:
                actual_value = stat.rebounds + stat.assists
        
        # Only skip if actual_value is None (not if it's 0, which is valid)
        if actual_value is None:
            return {
                'evaluated': False,
                'reason': f'Stat type {prediction.stat_type} not available (None in database)'
            }
        
        # Update prediction with actual result
        # Convert to int, handling both int and float values
        prediction.actual_result = int(actual_value) if actual_value is not None else None
        
        # Evaluate each bet type
        hit_safe = None
        hit_standard = None
        hit_long_shot = None
        
        if prediction.safe_line is not None:
            # Safe bet is typically "Over" - check if actual >= line
            hit_safe = actual_value >= prediction.safe_line
            prediction.hit_safe = hit_safe
        
        if prediction.standard_line is not None:
            # Standard bet is typically "Over" - check if actual >= line
            hit_standard = actual_value >= prediction.standard_line
            prediction.hit_standard = hit_standard
        
        if prediction.long_shot_line is not None:
            # Long shot bet is typically "Over" - check if actual >= line
            hit_long_shot = actual_value >= prediction.long_shot_line
            prediction.hit_long_shot = hit_long_shot
        
        return {
            'evaluated': True,
            'actual_result': actual_value,
            'hit_safe': hit_safe,
            'hit_standard': hit_standard,
            'hit_long_shot': hit_long_shot,
            'safe_line': prediction.safe_line,
            'standard_line': prediction.standard_line,
            'long_shot_line': prediction.long_shot_line
        }
    
    def evaluate_game(self, game_id: int) -> Dict[str, int]:
        """
        Evaluate all predictions for a game.
        
        ENHANCEMENT: Also evaluates games with box scores even if status isn't 'finished'
        (some games may have box scores but status hasn't been updated yet)
        
        Returns:
            Dict with counts of evaluated predictions
        """
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return {
                'evaluated': 0,
                'skipped': 0,
                'errors': 0
            }
        
        # Check if game is finished OR has box scores (indicating it's actually finished)
        from app.models.player_game_stat import PlayerGameStat
        has_box_scores = self.db.query(PlayerGameStat).filter(
            PlayerGameStat.game_id == game_id
        ).first() is not None
        
        # Allow evaluation if game is finished OR has box scores
        if game.game_status != 'finished' and not has_box_scores:
            return {
                'evaluated': 0,
                'skipped': 0,
                'errors': 0
            }
        
        # If game has box scores but status isn't 'finished', update the status
        if has_box_scores and game.game_status != 'finished':
            print(f"  ⚠️  Game {game_id} has box scores but status is '{game.game_status}'. Updating to 'finished'.")
            game.game_status = 'finished'
            self.db.add(game)
        
        predictions = self.db.query(Prediction).filter(
            Prediction.game_id == game_id
        ).all()
        
        evaluated = 0
        skipped = 0
        errors = 0
        
        for pred in predictions:
            try:
                result = self.evaluate_prediction(pred)
                if result['evaluated']:
                    evaluated += 1
                    # Add the prediction to the session if it's not already tracked
                    if pred not in self.db:
                        self.db.add(pred)
                else:
                    skipped += 1
            except Exception as e:
                print(f"Error evaluating prediction {pred.prediction_id}: {e}")
                errors += 1
        
        try:
            if evaluated > 0:
                self.db.commit()
        except Exception as e:
            print(f"Error committing evaluation results: {e}")
            self.db.rollback()
            raise
        
        return {
            'evaluated': evaluated,
            'skipped': skipped,
            'errors': errors
        }
    
    def evaluate_date(self, target_date: date) -> Dict[str, int]:
        """
        Evaluate all predictions for finished games on a specific date.
        Also includes games with box scores even if status isn't 'finished'.
        
        Returns:
            Dict with summary statistics
        """
        from app.models.player_game_stat import PlayerGameStat
        from sqlalchemy import or_
        
        # Get game IDs that have box scores
        games_with_box_scores = self.db.query(PlayerGameStat.game_id).distinct().subquery()
        
        # Query games that are finished OR have box scores
        games = self.db.query(Game).filter(
            and_(
                Game.game_date == target_date,
                or_(
                    Game.game_status == 'finished',
                    Game.game_id.in_(self.db.query(games_with_box_scores.c.game_id))
                )
            )
        ).all()
        
        total_evaluated = 0
        total_skipped = 0
        total_errors = 0
        
        for game in games:
            result = self.evaluate_game(game.game_id)
            total_evaluated += result['evaluated']
            total_skipped += result['skipped']
            total_errors += result['errors']
        
        return {
            'games_processed': len(games),
            'evaluated': total_evaluated,
            'skipped': total_skipped,
            'errors': total_errors
        }
    
    def get_prediction_results(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        bet_type: Optional[str] = None,
        stat_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Get historical prediction results with evaluation data.
        
        Args:
            start_date: Start date for filtering (default: 30 days ago)
            end_date: End date for filtering (default: today)
            bet_type: Filter by bet type (safe, standard, long_shot)
            stat_type: Filter by stat type (points, rebounds, assists)
        
        Returns:
            List of prediction results with evaluation data
        """
        if start_date is None:
            start_date = date.today() - timedelta(days=30)
        if end_date is None:
            end_date = date.today()
        
        # ENHANCEMENT: Query predictions for finished games OR games with box scores
        # Some games may have box scores but status hasn't been updated to 'finished' yet
        from app.models.player_game_stat import PlayerGameStat
        from sqlalchemy import or_
        
        # Get game IDs that have box scores
        games_with_box_scores = self.db.query(PlayerGameStat.game_id).distinct().subquery()
        
        # Query predictions for finished games OR games with box scores
        # Exclude "pass" predictions by default (they weren't recommended bets)
        # Show both evaluated and unevaluated predictions (unevaluated will have actual_result=None)
        query = self.db.query(Prediction).join(Game).filter(
            and_(
                Game.game_date >= start_date,
                Game.game_date <= end_date,
                # Include if finished OR has box scores
                or_(
                    Game.game_status == 'finished',
                    Game.game_id.in_(self.db.query(games_with_box_scores.c.game_id))
                ),
                Prediction.bet_type != 'pass'  # Exclude pass predictions (not recommended bets)
            )
        )
        
        if bet_type:
            query = query.filter(Prediction.bet_type == bet_type)
        
        if stat_type:
            query = query.filter(Prediction.stat_type == stat_type)
        
        predictions = query.order_by(Game.game_date.desc(), Game.game_id).limit(1000).all()  # Limit to prevent huge queries
        
        from app.models.team import Team
        
        # Batch load all related data to avoid N+1 queries
        player_ids = list(set([p.player_id for p in predictions]))
        game_ids = list(set([p.game_id for p in predictions]))
        
        players = {p.player_id: p for p in self.db.query(Player).filter(Player.player_id.in_(player_ids)).all()}
        games = {g.game_id: g for g in self.db.query(Game).filter(Game.game_id.in_(game_ids)).all()}
        
        # Get all team IDs
        team_ids = set()
        for game in games.values():
            team_ids.add(game.home_team_id)
            team_ids.add(game.away_team_id)
        
        teams = {t.team_id: t for t in self.db.query(Team).filter(Team.team_id.in_(list(team_ids))).all()}
        
        # Batch load player stats to avoid N+1 queries
        # Load stats for ALL predictions (needed for void detection even if actual_result is set)
        from app.models.player_game_stat import PlayerGameStat
        player_stat_ids = [
            (p.player_id, p.game_id) for p in predictions
        ]
        player_stats = {}
        if player_stat_ids:
            # Build filter conditions
            from sqlalchemy import or_
            conditions = []
            for pid, gid in player_stat_ids:
                conditions.append(
                    and_(
                        PlayerGameStat.player_id == pid,
                        PlayerGameStat.game_id == gid
                    )
                )
            
            if conditions:
                stat_query = self.db.query(PlayerGameStat).filter(or_(*conditions)).all()
                for stat in stat_query:
                    player_stats[(stat.player_id, stat.game_id)] = stat
        
        results = []
        for pred in predictions:
            player = players.get(pred.player_id)
            game = games.get(pred.game_id)
            
            # Get team info for game
            home_team = None
            away_team = None
            game_matchup = None
            if game:
                home_team = teams.get(game.home_team_id)
                away_team = teams.get(game.away_team_id)
                if home_team and away_team:
                    game_matchup = f"{away_team.abbreviation} @ {home_team.abbreviation}"
            
            # FIRST: Check if player actually played (void detection)
            # This must happen BEFORE we check hit status from database
            actual_result = pred.actual_result
            is_void = False
            
            # Check if game is finished and has box scores
            game_has_box_scores = False
            if game:
                # Check if any player has stats for this game (indicates box scores exist)
                stats_count = self.db.query(func.count(PlayerGameStat.stat_id)).filter(
                    PlayerGameStat.game_id == pred.game_id
                ).scalar()
                game_has_box_scores = stats_count > 0
            
            # Try to get from player stats
            stat = player_stats.get((pred.player_id, pred.game_id))
            
            if stat:
                # Player has stats - check if they actually played (minutes > 0)
                if stat.minutes_played is not None and stat.minutes_played > 0:
                    # Player played - get actual stat if we don't have it
                    if actual_result is None:
                        if pred.stat_type == 'points':
                            actual_result = stat.points if stat.points is not None else None
                        elif pred.stat_type == 'rebounds':
                            actual_result = stat.rebounds if stat.rebounds is not None else None
                        elif pred.stat_type == 'assists':
                            actual_result = stat.assists if stat.assists is not None else None
                        elif pred.stat_type == 'minutes':
                            actual_result = stat.minutes_played if stat.minutes_played is not None else None
                        elif pred.stat_type == 'points_rebounds':
                            # Combo: points + rebounds
                            if stat.points is not None and stat.rebounds is not None:
                                actual_result = stat.points + stat.rebounds
                        elif pred.stat_type == 'points_assists':
                            # Combo: points + assists
                            if stat.points is not None and stat.assists is not None:
                                actual_result = stat.points + stat.assists
                        elif pred.stat_type == 'rebounds_assists':
                            # Combo: rebounds + assists
                            if stat.rebounds is not None and stat.assists is not None:
                                actual_result = stat.rebounds + stat.assists
                else:
                    # Player has stats but minutes_played is 0 or None - they didn't play
                    is_void = True
            elif game_has_box_scores:
                # Game has box scores but this player doesn't have stats - they didn't play
                is_void = True
            
            # If player didn't play, mark as void immediately (OVERRIDE any existing hit status)
            if is_void:
                # CRITICAL: Void status overrides any existing hit/miss status
                # Clear any existing hit values to prevent confusion
                needs_update = False
                if pred.bet_type == 'safe' and pred.hit_safe is not None:
                    pred.hit_safe = None
                    needs_update = True
                elif pred.bet_type == 'standard' and pred.hit_standard is not None:
                    pred.hit_standard = None
                    needs_update = True
                elif pred.bet_type == 'long_shot' and pred.hit_long_shot is not None:
                    pred.hit_long_shot = None
                    needs_update = True
                
                # Also clear actual_result if it was incorrectly set
                if pred.actual_result is not None:
                    pred.actual_result = None
                    needs_update = True
                
                # Commit the changes to database
                if needs_update:
                    if pred not in self.db:
                        self.db.add(pred)
                    self.db.flush()  # Flush to ensure changes are saved
                
                final_hit = 'void'  # Always void if player didn't play
                line = None
                probability = None
                # Get line and probability for display purposes
                if pred.bet_type == 'safe':
                    line = pred.safe_line
                    probability = pred.safe_probability
                elif pred.bet_type == 'standard':
                    line = pred.standard_line
                    probability = pred.standard_probability
                elif pred.bet_type == 'long_shot':
                    line = pred.long_shot_line
                    probability = pred.long_shot_probability
            else:
                # Player played - determine which bet hit based on bet_type
                hit = None
                line = None
                probability = None
                
                if pred.bet_type == 'safe':
                    hit = pred.hit_safe
                    line = pred.safe_line
                    probability = pred.safe_probability
                elif pred.bet_type == 'standard':
                    hit = pred.hit_standard
                    line = pred.standard_line
                    probability = pred.standard_probability
                elif pred.bet_type == 'long_shot':
                    hit = pred.hit_long_shot
                    line = pred.long_shot_line
                    probability = pred.long_shot_probability
                
                # If we have actual_result but hit is not set, evaluate it now
                if actual_result is not None and hit is None and line is not None:
                    if pred.bet_type == 'safe' and pred.safe_line is not None:
                        hit = actual_result >= pred.safe_line
                        pred.hit_safe = hit
                    elif pred.bet_type == 'standard' and pred.standard_line is not None:
                        hit = actual_result >= pred.standard_line
                        pred.hit_standard = hit
                    elif pred.bet_type == 'long_shot' and pred.long_shot_line is not None:
                        hit = actual_result >= pred.long_shot_line
                        pred.hit_long_shot = hit
                    
                    # Update actual_result in database if needed
                    if pred.actual_result is None:
                        pred.actual_result = int(actual_result)
                    
                    # Add to session if not already tracked
                    if pred not in self.db:
                        self.db.add(pred)
                
                final_hit = hit
            
            results.append({
                'prediction_id': pred.prediction_id,
                'player_id': pred.player_id,
                'player_name': player.name if player else f"Player {pred.player_id}",
                'game_id': pred.game_id,
                'game_date': game.game_date.isoformat() if game else None,
                'game_matchup': game_matchup,
                'home_team': home_team.abbreviation if home_team else None,
                'away_team': away_team.abbreviation if away_team else None,
                'stat_type': pred.stat_type,
                'bet_type': pred.bet_type,
                'line': line,
                'predicted_mean': pred.distribution_mean,
                'predicted_std': pred.distribution_std_dev,
                'actual_result': actual_result,
                'hit': final_hit,  # Can be True, False, None (pending), or 'void'
                'probability': probability,
                'confidence_level': pred.confidence_level,
                'volatility_level': pred.volatility_level
            })
        
        # Commit any updates we made (actual_result, hit status, void status)
        # Check if any predictions were modified
        has_updates = False
        for pred in predictions:
            # Check if prediction is in session and was modified
            if pred in self.db:
                # We've made changes (actual_result, hit status, or void status)
                has_updates = True
                break
        
        if has_updates:
            try:
                self.db.commit()
            except Exception as e:
                print(f"Error committing prediction updates: {e}")
                self.db.rollback()
        
        return results
    
    def get_accuracy_stats(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        bet_type: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Get accuracy statistics for predictions.
        
        Only includes predictions that have been evaluated (hit is True or False).
        Unevaluated predictions (hit is None) are excluded from accuracy calculations.
        
        Returns:
            Dict with accuracy metrics including evaluated vs unevaluated counts
        """
        results = self.get_prediction_results(start_date, end_date, bet_type)
        
        if not results:
            return {
                'total': 0,
                'evaluated': 0,
                'unevaluated': 0,
                'hits': 0,
                'misses': 0,
                'accuracy': 0.0,
                'by_bet_type': {}
            }
        
        # Separate evaluated from unevaluated
        # Separate evaluated (hits/misses), void, and pending
        # Voids are excluded from accuracy calculations (they don't count as hits or misses)
        evaluated_results = [r for r in results if r['hit'] is True or r['hit'] is False]
        void_results = [r for r in results if r['hit'] == 'void']
        unevaluated_results = [r for r in results if r['hit'] is None]
        
        # Calculate stats only from evaluated predictions (exclude voids)
        hits = sum(1 for r in evaluated_results if r['hit'] is True)
        misses = sum(1 for r in evaluated_results if r['hit'] is False)
        evaluated_total = len(evaluated_results)
        total = len(results)  # Total includes both evaluated and unevaluated
        
        # Group by bet type - separate evaluated from unevaluated
        by_bet_type = {}
        for result in results:
            bt = result['bet_type']
            if bt not in by_bet_type:
                by_bet_type[bt] = {
                    'hits': 0, 
                    'misses': 0, 
                    'evaluated': 0,  # Only evaluated predictions
                    'unevaluated': 0,  # Predictions without box scores
                    'total': 0  # Total (evaluated + unevaluated)
                }
            
            by_bet_type[bt]['total'] += 1
            
            # Only count hits/misses for accuracy (exclude voids)
            if result['hit'] is True or result['hit'] is False:
                # This prediction has been evaluated (hit or miss)
                by_bet_type[bt]['evaluated'] += 1
                if result['hit'] is True:
                    by_bet_type[bt]['hits'] += 1
                elif result['hit'] is False:
                    by_bet_type[bt]['misses'] += 1
            elif result['hit'] == 'void':
                # Void predictions don't count toward accuracy
                pass  # Don't increment evaluated or unevaluated
            else:
                # This prediction hasn't been evaluated yet
                by_bet_type[bt]['unevaluated'] += 1
        
        # Calculate accuracy for each bet type (only using evaluated predictions)
        for bt in by_bet_type:
            bt_data = by_bet_type[bt]
            evaluated_count = bt_data['evaluated']
            if evaluated_count > 0:
                bt_data['accuracy'] = (bt_data['hits'] / evaluated_count * 100)
            else:
                bt_data['accuracy'] = 0.0
        
        return {
            'total': total,  # Total predictions (evaluated + unevaluated + void)
            'evaluated': evaluated_total,  # Only evaluated predictions (hits/misses)
            'unevaluated': len(unevaluated_results),  # Predictions without box scores
            'void': len(void_results),  # Predictions for players who didn't play
            'hits': hits,
            'misses': misses,
            'accuracy': (hits / evaluated_total * 100) if evaluated_total > 0 else 0.0,  # Only from evaluated
            'by_bet_type': by_bet_type
        }

