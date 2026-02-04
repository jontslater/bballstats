"""
Betting Line Service

Compares our predictions to actual betting lines and identifies value bets.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Dict, Optional
from app.models.betting_line import BettingLine
from app.models.prediction import Prediction
from app.models.game import Game
from app.models.player import Player


class BettingLineService:
    """Service for managing betting lines and value analysis."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def add_betting_line(
        self,
        game_id: int,
        player_id: int,
        stat_type: str,
        over_line: float,
        over_odds: str = "-110",
        under_odds: str = "-110",
        sportsbook: str = "DraftKings"
    ) -> BettingLine:
        """
        Add or update a betting line.
        
        Returns:
            BettingLine object
        """
        # Check for existing line
        existing = self.db.query(BettingLine).filter(
            and_(
                BettingLine.game_id == game_id,
                BettingLine.player_id == player_id,
                BettingLine.stat_type == stat_type,
                BettingLine.sportsbook == sportsbook
            )
        ).first()
        
        if existing:
            existing.over_line = over_line
            existing.under_line = over_line  # Usually same
            existing.over_odds = over_odds
            existing.under_odds = under_odds
            self.db.commit()
            self.db.refresh(existing)
            return existing
        
        # Create new line
        betting_line = BettingLine(
            game_id=game_id,
            player_id=player_id,
            stat_type=stat_type,
            over_line=over_line,
            under_line=over_line,
            over_odds=over_odds,
            under_odds=under_odds,
            sportsbook=sportsbook
        )
        
        self.db.add(betting_line)
        self.db.commit()
        self.db.refresh(betting_line)
        
        return betting_line
    
    def calculate_value(
        self,
        our_prediction: float,
        our_probability: float,
        betting_line: float,
        betting_odds: str
    ) -> Dict[str, float]:
        """
        Calculate value score for a bet.
        
        Value = (Our Probability * Implied Odds) - (Betting Line Probability * Implied Odds)
        Positive value = good bet, negative value = bad bet
        
        Returns:
            Dict with value_score, edge, and recommendation
        """
        # Convert odds to implied probability
        implied_prob = self._odds_to_probability(betting_odds)
        
        # Calculate expected value
        # EV = (Our Prob * Win Amount) - (Betting Prob * Loss Amount)
        if betting_odds.startswith('-'):
            # Negative odds (favorite)
            odds_num = abs(int(betting_odds))
            win_amount = 100  # Bet $110 to win $100
            loss_amount = 110
        else:
            # Positive odds (underdog)
            odds_num = int(betting_odds.replace('+', ''))
            win_amount = odds_num  # Bet $100 to win $odds_num
            loss_amount = 100
        
        # Expected value calculation
        ev = (our_probability * win_amount) - ((1 - our_probability) * loss_amount)
        
        # Value score (normalized)
        value_score = ev / 100.0  # Normalize to -1 to +1 range
        
        # Edge (how much better our probability is)
        edge = our_probability - implied_prob
        
        # Recommendation
        if value_score > 0.05 and edge > 0.05:  # 5%+ edge
            recommendation = "STRONG_VALUE"
        elif value_score > 0.02 and edge > 0.02:  # 2%+ edge
            recommendation = "VALUE"
        elif value_score > -0.02:  # Close to fair
            recommendation = "FAIR"
        else:  # Negative value
            recommendation = "NO_VALUE"
        
        return {
            'value_score': round(value_score, 4),
            'edge': round(edge, 4),
            'expected_value': round(ev, 2),
            'implied_probability': round(implied_prob, 4),
            'our_probability': round(our_probability, 4),
            'recommendation': recommendation
        }
    
    def _odds_to_probability(self, odds: str) -> float:
        """Convert American odds to implied probability."""
        if odds.startswith('-'):
            # Negative odds: -110 means bet $110 to win $100
            odds_num = abs(int(odds))
            prob = odds_num / (odds_num + 100)
        else:
            # Positive odds: +150 means bet $100 to win $150
            odds_num = int(odds.replace('+', ''))
            prob = 100 / (odds_num + 100)
        
        return prob
    
    def find_value_bets(
        self,
        game_id: Optional[int] = None,
        stat_type: Optional[str] = None,
        min_value_score: float = 0.02
    ) -> List[Dict]:
        """
        Find bets where our prediction shows value vs betting lines.
        
        Returns:
            List of value bet dictionaries
        """
        # Get all betting lines
        query = self.db.query(BettingLine)
        
        if game_id:
            query = query.filter(BettingLine.game_id == game_id)
        if stat_type:
            query = query.filter(BettingLine.stat_type == stat_type)
        
        betting_lines = query.all()
        
        value_bets = []
        
        for line in betting_lines:
            # Get our prediction for this player/stat/game
            prediction = self.db.query(Prediction).filter(
                and_(
                    Prediction.game_id == line.game_id,
                    Prediction.player_id == line.player_id,
                    Prediction.stat_type == line.stat_type,
                    Prediction.bet_type.in_(['safe', 'standard', 'long_shot'])
                )
            ).first()
            
            if not prediction or not line.over_line:
                continue
            
            # Determine which line to compare
            # Compare our safe/standard/long_shot line to betting line
            if prediction.bet_type == 'safe' and prediction.safe_line:
                our_line = prediction.safe_line
                our_prob = prediction.safe_probability
            elif prediction.bet_type == 'standard' and prediction.standard_line:
                our_line = prediction.standard_line
                our_prob = prediction.standard_probability
            elif prediction.bet_type == 'long_shot' and prediction.long_shot_line:
                our_line = prediction.long_shot_line
                our_prob = prediction.long_shot_probability
            else:
                continue
            
            # Calculate value
            value_analysis = self.calculate_value(
                our_prediction=our_line,
                our_probability=our_prob,
                betting_line=line.over_line,
                betting_odds=line.over_odds or "-110"
            )
            
            # Update line with our prediction and value
            line.our_prediction = our_line
            line.our_probability = our_prob
            line.value_score = value_analysis['value_score']
            self.db.commit()
            
            # Only include if value score meets threshold
            if value_analysis['value_score'] >= min_value_score:
                player = self.db.query(Player).filter(Player.player_id == line.player_id).first()
                game = self.db.query(Game).filter(Game.game_id == line.game_id).first()
                
                value_bets.append({
                    'betting_line_id': line.line_id,
                    'game_id': line.game_id,
                    'player_id': line.player_id,
                    'player_name': player.name if player else f"Player {line.player_id}",
                    'stat_type': line.stat_type,
                    'betting_line': line.over_line,
                    'betting_odds': line.over_odds,
                    'our_prediction': our_line,
                    'our_probability': our_prob,
                    'value_score': value_analysis['value_score'],
                    'edge': value_analysis['edge'],
                    'recommendation': value_analysis['recommendation'],
                    'sportsbook': line.sportsbook,
                    'game_date': game.game_date if game else None
                })
        
        # Sort by value score (highest first)
        value_bets.sort(key=lambda x: x['value_score'], reverse=True)
        
        return value_bets
    
    def compare_prediction_to_line(
        self,
        prediction_id: int,
        betting_line_id: int
    ) -> Dict:
        """
        Compare a specific prediction to a betting line.
        
        Returns:
            Comparison analysis
        """
        prediction = self.db.query(Prediction).filter(Prediction.prediction_id == prediction_id).first()
        betting_line = self.db.query(BettingLine).filter(BettingLine.line_id == betting_line_id).first()
        
        if not prediction or not betting_line:
            return {'error': 'Prediction or betting line not found'}
        
        # Determine which line to use
        if prediction.bet_type == 'safe':
            our_line = prediction.safe_line
            our_prob = prediction.safe_probability
        elif prediction.bet_type == 'standard':
            our_line = prediction.standard_line
            our_prob = prediction.standard_probability
        elif prediction.bet_type == 'long_shot':
            our_line = prediction.long_shot_line
            our_prob = prediction.long_shot_probability
        else:
            return {'error': 'Invalid bet type'}
        
        value_analysis = self.calculate_value(
            our_prediction=our_line,
            our_probability=our_prob,
            betting_line=betting_line.over_line,
            betting_odds=betting_line.over_odds or "-110"
        )
        
        return {
            'prediction_id': prediction_id,
            'betting_line_id': betting_line_id,
            'our_line': our_line,
            'our_probability': our_prob,
            'betting_line': betting_line.over_line,
            'betting_odds': betting_line.over_odds,
            'line_difference': round(our_line - betting_line.over_line, 2),
            'value_analysis': value_analysis
        }





