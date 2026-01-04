"""
Parlay Evaluator - Evaluate parlay bets against actual game results.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Dict, Optional
from datetime import date, timedelta
from app.models.parlay import Parlay
from app.models.user_play import UserPlay
from app.models.game import Game
from app.models.player_game_stat import PlayerGameStat
from app.models.prediction import Prediction
import re
import logging

logger = logging.getLogger(__name__)


class ParlayEvaluator:
    """Evaluate parlay bets against actual game results."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def evaluate_parlay(self, parlay: Parlay) -> Dict:
        """
        Evaluate a single parlay.
        
        Args:
            parlay: Parlay object to evaluate
            
        Returns:
            Dict with evaluation results
        """
        if not parlay.plays:
            return {
                'parlay_id': parlay.parlay_id,
                'status': 'error',
                'error': 'No plays found in parlay'
            }
        
        legs_hit = 0
        legs_missed = 0
        legs_pending = 0
        leg_results = []
        
        for play in parlay.plays:
            # Get the game
            game = self.db.query(Game).filter(Game.game_id == play.game_id).first()
            if not game:
                leg_results.append({
                    'play_id': play.play_id,
                    'status': 'error',
                    'error': 'Game not found'
                })
                legs_pending += 1
                continue
            
            # Check if game is finished
            if game.game_status != 'finished':
                leg_results.append({
                    'play_id': play.play_id,
                    'status': 'pending',
                    'reason': 'Game not finished'
                })
                legs_pending += 1
                continue
            
            # Get actual stats for this player in this game
            stat = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.player_id == play.player_id,
                    PlayerGameStat.game_id == play.game_id,
                    PlayerGameStat.minutes_played > 0  # Player actually played
                )
            ).first()
            
            if not stat:
                # Player didn't play - leg is void (doesn't count against parlay)
                leg_results.append({
                    'play_id': play.play_id,
                    'status': 'void',
                    'reason': 'Player did not play',
                    'actual_result': None
                })
                # Voids don't count as misses - continue without incrementing legs_missed
                continue
            
            # Evaluate the bet line
            hit = self._evaluate_bet_line(play, stat)
            
            # Update play status
            if play.status == 'pending':
                play.status = 'hit' if hit else 'miss'
                play.actual_result = self._get_actual_stat(play, stat)
            
            leg_results.append({
                'play_id': play.play_id,
                'status': 'hit' if hit else 'miss',
                'actual_result': self._get_actual_stat(play, stat),
                'bet_line': play.bet_line
            })
            
            if hit:
                legs_hit += 1
            else:
                legs_missed += 1
        
        # Determine parlay status
        # Count non-void legs for evaluation
        non_void_legs = parlay.total_legs - sum(1 for leg in leg_results if leg.get('status') == 'void')
        non_void_pending = sum(1 for leg in leg_results if leg.get('status') == 'pending')
        
        if non_void_pending > 0:
            status = 'pending'
        elif legs_missed > 0:
            status = 'miss'
        elif non_void_legs > 0 and legs_hit == non_void_legs:
            # All non-void legs hit = parlay hits (voids don't count)
            status = 'hit'
        else:
            status = 'pending'
        
        # Update parlay
        parlay.legs_hit = legs_hit
        parlay.status = status
        
        return {
            'parlay_id': parlay.parlay_id,
            'name': parlay.name,
            'status': status,
            'legs_hit': legs_hit,
            'legs_missed': legs_missed,
            'legs_pending': legs_pending,
            'total_legs': parlay.total_legs,
            'leg_results': leg_results
        }
    
    def _evaluate_bet_line(self, play: UserPlay, stat: PlayerGameStat) -> bool:
        """
        Evaluate if a bet line hit or missed.
        
        Args:
            play: UserPlay object with bet_line
            stat: PlayerGameStat with actual results
            
        Returns:
            True if bet hit, False if missed
        """
        if not play.bet_line:
            return False
        
        # Get actual stat value
        actual_value = self._get_actual_stat(play, stat)
        if actual_value is None:
            return False
        
        # Parse bet line (e.g., "Over 24.5", "Under 10.5", "Over 8", "Under 15")
        bet_line = play.bet_line.strip()
        
        # Match patterns like "Over 24.5", "Under 10.5", "Over 8", "Under 15"
        over_match = re.match(r'^Over\s+([\d.]+)$', bet_line, re.IGNORECASE)
        under_match = re.match(r'^Under\s+([\d.]+)$', bet_line, re.IGNORECASE)
        
        if over_match:
            line_value = float(over_match.group(1))
            return actual_value > line_value
        elif under_match:
            line_value = float(under_match.group(1))
            return actual_value < line_value
        else:
            # Try to handle other formats
            # For combo bets, we'd need more complex logic
            if play.stat_type == 'combo':
                # Combo bets like "Points + Rebounds Over 20.5"
                # For now, just check if we can parse it
                logger.warning(f"Combo bet evaluation not fully implemented: {bet_line}")
                return False
            
            # Default: try to extract number and assume "Over"
            number_match = re.search(r'([\d.]+)', bet_line)
            if number_match:
                line_value = float(number_match.group(1))
                return actual_value > line_value
            
            return False
    
    def _get_actual_stat(self, play: UserPlay, stat: PlayerGameStat) -> Optional[float]:
        """
        Get the actual stat value for a play.
        
        Args:
            play: UserPlay object
            stat: PlayerGameStat with actual results
            
        Returns:
            Actual stat value or None
        """
        if play.stat_type == 'points':
            return stat.points
        elif play.stat_type == 'rebounds':
            return stat.rebounds
        elif play.stat_type == 'assists':
            return stat.assists
        elif play.stat_type == 'minutes':
            return stat.minutes_played
        elif play.stat_type == 'combo':
            # Points + Rebounds or Points + Assists, etc.
            # Parse from bet_line or use a default
            if 'points' in play.bet_line.lower() and 'rebounds' in play.bet_line.lower():
                return (stat.points or 0) + (stat.rebounds or 0)
            elif 'points' in play.bet_line.lower() and 'assists' in play.bet_line.lower():
                return (stat.points or 0) + (stat.assists or 0)
            elif 'rebounds' in play.bet_line.lower() and 'assists' in play.bet_line.lower():
                return (stat.rebounds or 0) + (stat.assists or 0)
            else:
                return None
        else:
            return None
    
    def evaluate_all_finished_parlays(self, days_back: Optional[int] = None) -> Dict:
        """
        Evaluate all parlays for finished games.
        
        Args:
            days_back: Only evaluate parlays for games within this many days (None = all)
            
        Returns:
            Dict with evaluation summary
        """
        # Get all parlays
        query = self.db.query(Parlay).filter(Parlay.status == 'pending')
        
        parlays = query.all()
        
        evaluated = 0
        hits = 0
        misses = 0
        still_pending = 0
        errors = 0
        
        for parlay in parlays:
            try:
                # Check if all games are finished
                all_finished = True
                for play in parlay.plays:
                    game = self.db.query(Game).filter(Game.game_id == play.game_id).first()
                    if not game or game.game_status != 'finished':
                        all_finished = False
                        break
                
                if not all_finished:
                    still_pending += 1
                    continue
                
                # Evaluate the parlay
                result = self.evaluate_parlay(parlay)
                
                if result['status'] == 'hit':
                    hits += 1
                elif result['status'] == 'miss':
                    misses += 1
                elif result['status'] == 'pending':
                    still_pending += 1
                else:
                    errors += 1
                
                evaluated += 1
                
            except Exception as e:
                logger.error(f"Error evaluating parlay {parlay.parlay_id}: {e}")
                errors += 1
        
        # Commit all changes
        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Error committing parlay evaluations: {e}")
            self.db.rollback()
        
        return {
            'total_parlays': len(parlays),
            'evaluated': evaluated,
            'hits': hits,
            'misses': misses,
            'still_pending': still_pending,
            'errors': errors
        }
    
    def evaluate_parlays_for_game(self, game_id: int) -> Dict:
        """
        Evaluate all parlays that include plays from a specific game.
        
        Args:
            game_id: Game ID to evaluate parlays for
            
        Returns:
            Dict with evaluation summary
        """
        # Get all parlays that have at least one play for this game
        parlays = self.db.query(Parlay).join(
            UserPlay, Parlay.plays
        ).filter(
            UserPlay.game_id == game_id
        ).distinct().all()
        
        evaluated = 0
        hits = 0
        misses = 0
        still_pending = 0
        
        for parlay in parlays:
            try:
                result = self.evaluate_parlay(parlay)
                
                if result['status'] == 'hit':
                    hits += 1
                elif result['status'] == 'miss':
                    misses += 1
                else:
                    still_pending += 1
                
                evaluated += 1
                
            except Exception as e:
                logger.error(f"Error evaluating parlay {parlay.parlay_id}: {e}")
        
        # Commit all changes
        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Error committing parlay evaluations: {e}")
            self.db.rollback()
        
        return {
            'game_id': game_id,
            'total_parlays': len(parlays),
            'evaluated': evaluated,
            'hits': hits,
            'misses': misses,
            'still_pending': still_pending
        }

