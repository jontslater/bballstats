"""
Poor Man's Bet Service

Service for managing Poor Man's Bet challenges - compound small amounts daily using very safe bets.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from typing import Dict, List, Optional, Tuple
from datetime import date, timedelta
from decimal import Decimal
import math

from app.models.poor_mans_bet import PoorMansBetChallenge, PoorMansBetDay
from app.models.prediction import Prediction
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team
from app.models.parlay import Parlay
from app.models.user_play import UserPlay


class PoorMansBetService:
    """Service for Poor Man's Bet challenges."""
    
    def __init__(self, db: Session):
        self.db = db
        self.daily_multiplier = 1.51  # 200^(1/14) for 14-day challenge
        self.max_bet_percentage = 0.70  # 70% of bankroll maximum
        self.min_bet_amount = Decimal('1.00')
    
    def create_challenge(
        self,
        start_amount: Decimal,
        days_target: int = 14,
        name: Optional[str] = None
    ) -> PoorMansBetChallenge:
        """
        Create a new Poor Man's Bet challenge.
        
        Args:
            start_amount: Starting amount ($1-$5)
            days_target: Number of days (default 14)
            name: Optional name for the challenge
        
        Returns:
            Created challenge
        """
        # Calculate target amount (200x growth)
        target_amount = start_amount * Decimal('200')
        
        # Calculate target date
        start_date = date.today()
        target_date = start_date + timedelta(days=days_target)
        
        challenge = PoorMansBetChallenge(
            name=name or f"Poor Man's Bet - ${start_amount} to ${target_amount}",
            start_amount=start_amount,
            target_amount=target_amount,
            days_target=days_target,
            current_bankroll=start_amount,
            status='active',
            start_date=start_date,
            target_date=target_date,
            current_day=1
        )
        
        self.db.add(challenge)
        self.db.commit()
        self.db.refresh(challenge)
        
        return challenge
    
    def get_daily_bet_suggestion(
        self,
        challenge_id: int,
        game_date: Optional[date] = None,
        allow_multiple: bool = True
    ) -> Optional[Dict]:
        """
        Get suggested bet(s) for a challenge day.
        
        This finds the safest bets and builds optimal parlays. If allow_multiple is True,
        returns suggestions grouped by game time slots (early, mid, late games).
        
        Args:
            challenge_id: Challenge ID
            game_date: Date to get bets for (default: today)
            allow_multiple: If True, return multiple suggestions for different time slots
        
        Returns:
            Dict with bet suggestion(s) or None if no safe bets available
            If allow_multiple=True, returns dict with 'suggestions' list and 'multiple' flag
        """
        if game_date is None:
            game_date = date.today()
        
        challenge = self.db.query(PoorMansBetChallenge).filter(
            PoorMansBetChallenge.challenge_id == challenge_id
        ).first()
        
        if not challenge:
            return None
        
        if challenge.status != 'active':
            return None
        
        # Get all safe bets for the date
        all_safe_bets = self._find_safest_bets(game_date, challenge.current_day)
        
        if not all_safe_bets:
            return None
        
        # Group bets by game time slot if allow_multiple
        if allow_multiple:
            from datetime import datetime, timezone
            from collections import defaultdict
            
            # Group by time slot (early: before 4pm, mid: 4pm-7pm, late: after 7pm)
            time_slots = defaultdict(list)
            
            for bet in all_safe_bets:
                if bet.get('game_time'):
                    try:
                        game_time = datetime.fromisoformat(bet['game_time'].replace('Z', '+00:00'))
                        hour = game_time.hour
                        if hour < 16:  # Before 4pm
                            time_slot = 'early'
                        elif hour < 19:  # 4pm-7pm
                            time_slot = 'mid'
                        else:  # After 7pm
                            time_slot = 'late'
                    except:
                        time_slot = 'all'  # Fallback if time parsing fails
                else:
                    time_slot = 'all'
                
                time_slots[time_slot].append(bet)
            
            # Build suggestions for each time slot that has safe bets
            suggestions = []
            for time_slot in ['early', 'mid', 'late']:
                if time_slot not in time_slots or len(time_slots[time_slot]) < 2:
                    continue
                
                # Get game IDs for this time slot
                time_slot_game_ids = list(set([bet['game_id'] for bet in time_slots[time_slot]]))
                
                # Build optimal parlay for this time slot
                parlay = self._build_optimal_parlay(time_slots[time_slot], challenge.current_day)
                
                if not parlay:
                    continue
                
                # Calculate bet amount (use current bankroll, which may include winnings from earlier bets)
                bet_amount = self._calculate_bet_amount(
                    challenge.current_bankroll,
                    self.daily_multiplier,
                    parlay['expected_return_multiplier']
                )
                
                if bet_amount < self.min_bet_amount:
                    continue
                
                expected_return = bet_amount * Decimal(str(parlay['expected_return_multiplier']))
                
                suggestions.append({
                    'time_slot': time_slot,
                    'challenge_id': challenge_id,
                    'day_number': challenge.current_day,
                    'game_date': game_date.isoformat(),
                    'current_bankroll': float(challenge.current_bankroll),
                    'bet_amount': float(bet_amount),
                    'expected_return': float(expected_return),
                    'bet_type': 'parlay',
                    'legs': parlay['legs'],
                    'combined_probability': parlay['combined_probability'],
                    'expected_return_multiplier': parlay['expected_return_multiplier'],
                    'reasoning': f"{time_slot.capitalize()} games: {parlay['num_legs']}-leg parlay with {parlay['combined_probability']*100:.1f}% combined probability"
                })
            
            # If we have multiple suggestions, return them all
            if len(suggestions) > 1:
                return {
                    'multiple': True,
                    'suggestions': suggestions,
                    'challenge_id': challenge_id,
                    'day_number': challenge.current_day,
                    'game_date': game_date.isoformat()
                }
            # If only one time slot has bets, return single suggestion (backwards compatible)
            elif len(suggestions) == 1:
                return suggestions[0]
        
        # Fallback to single suggestion (original behavior)
        parlay = self._build_optimal_parlay(all_safe_bets, challenge.current_day)
        
        if not parlay:
            return None
        
        bet_amount = self._calculate_bet_amount(
            challenge.current_bankroll,
            self.daily_multiplier,
            parlay['expected_return_multiplier']
        )
        
        if bet_amount < self.min_bet_amount:
            return None
        
        daily_target = challenge.current_bankroll * Decimal(str(self.daily_multiplier))
        expected_return = bet_amount * Decimal(str(parlay['expected_return_multiplier']))
        
        return {
            'challenge_id': challenge_id,
            'day_number': challenge.current_day,
            'game_date': game_date.isoformat(),
            'current_bankroll': float(challenge.current_bankroll),
            'daily_target': float(daily_target),
            'bet_amount': float(bet_amount),
            'expected_return': float(expected_return),
            'expected_bankroll_after': float(challenge.current_bankroll - bet_amount + expected_return),
            'bet_type': 'parlay',
            'legs': parlay['legs'],
            'combined_probability': parlay['combined_probability'],
            'expected_return_multiplier': parlay['expected_return_multiplier'],
            'reasoning': f"{parlay['num_legs']}-leg parlay with {parlay['combined_probability']*100:.1f}% combined probability"
        }
    
    def _find_safest_bets(self, game_date: date, current_day: int, game_ids: Optional[List[int]] = None) -> List[Dict]:
        """
        Find the safest bets for a given date (optionally filtered by game IDs).
        
        Criteria:
        - Probability: 75%+ (prefer 80%+)
        - Confidence Level: HIGH only
        - Volatility: LOW
        - Sample Size: 15+ games
        - Injury Status: Healthy
        - Lineup: Confirmed starter (for upcoming games)
        """
        # Get games for the date
        if game_ids is None:
            games = self.db.query(Game).filter(Game.game_date == game_date).all()
            game_ids = [g.game_id for g in games]
        
        if not game_ids:
            return []
        
        # Determine minimum probability based on day
        # Early days: prefer 80%+, later days can use 75%+
        # RELAXED: Allow 75%+ for all days if not enough 80%+ available
        min_probability = 0.80 if current_day <= 5 else 0.75
        
        # Get predictions with high safe probabilities
        # RELAXED: Allow MEDIUM volatility if not enough LOW volatility bets
        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id.in_(game_ids),
                Prediction.bet_type == 'safe',
                Prediction.stat_type.in_(['points', 'rebounds', 'assists']),
                Prediction.safe_probability >= min_probability,
                Prediction.confidence_level == 'HIGH',
                Prediction.volatility_level.in_(['LOW', 'MEDIUM'])  # Allow both LOW and MEDIUM
            )
        ).order_by(desc(Prediction.safe_probability)).limit(50).all()
        
        # Sort manually to prefer LOW volatility over MEDIUM
        # (In SQL, LOW < MEDIUM alphabetically, so we can't easily sort with CASE in all DBs)
        predictions = sorted(predictions, key=lambda p: (
            p.volatility_level != 'LOW',  # False (0) for LOW, True (1) for MEDIUM - LOW comes first
            -p.safe_probability  # Higher probability first
        ))
        
        # If we don't have enough with 80%+ threshold, relax to 75%+ for early days
        if current_day <= 5 and len(predictions) < 4:
            predictions = self.db.query(Prediction).filter(
                and_(
                    Prediction.game_id.in_(game_ids),
                    Prediction.bet_type == 'safe',
                    Prediction.stat_type.in_(['points', 'rebounds', 'assists']),
                    Prediction.safe_probability >= 0.75,
                    Prediction.confidence_level == 'HIGH',
                    Prediction.volatility_level.in_(['LOW', 'MEDIUM'])
                )
            ).order_by(desc(Prediction.safe_probability)).limit(50).all()
            
            # Sort manually to prefer LOW volatility
            predictions = sorted(predictions, key=lambda p: (
                p.volatility_level != 'LOW',  # LOW comes first
                -p.safe_probability
            ))
        
        # Filter out injured players
        from app.services.injury_context import InjuryContext
        injury_context = InjuryContext(self.db)
        
        safe_bets = []
        player_ids = list(set([p.player_id for p in predictions]))
        players_dict = {p.player_id: p for p in self.db.query(Player).filter(
            Player.player_id.in_(player_ids)
        ).all()}
        
        games_dict = {g.game_id: g for g in games}
        team_ids = list(set([p.current_team_id for p in players_dict.values() if p.current_team_id]))
        teams_dict = {t.team_id: t for t in self.db.query(Team).filter(
            Team.team_id.in_(team_ids)
        ).all()} if team_ids else {}
        
        for pred in predictions:
            # Check injury status
            injury_status = injury_context.get_player_injury_status(pred.player_id)
            if injury_status and injury_status['status'] in ['Out', 'Doubtful', 'Questionable']:
                continue
            
            player = players_dict.get(pred.player_id)
            game = games_dict.get(pred.game_id)
            
            if not player or not game:
                continue
            
            # Check sample size (should be in prediction, but verify)
            if pred.sample_size and pred.sample_size < 15:
                continue
            
            # Get player's team
            player_team = None
            if player.current_team_id:
                team = teams_dict.get(player.current_team_id)
                player_team = team.abbreviation if team else None
            
            # Get game time from schedule
            from app.models.game_schedule import GameSchedule
            schedule = self.db.query(GameSchedule).filter(
                GameSchedule.game_id == pred.game_id
            ).first()
            game_time = schedule.game_time if schedule else None
            
            safe_bets.append({
                'prediction_id': pred.prediction_id,
                'player_id': pred.player_id,
                'player_name': player.name,
                'player_team': player_team,
                'game_id': pred.game_id,
                'stat_type': pred.stat_type,
                'line': pred.safe_line,
                'probability': pred.safe_probability,
                'confidence_level': pred.confidence_level,
                'volatility_level': pred.volatility_level,
                'game_time': game_time.isoformat() if game_time else None
            })
        
        return safe_bets
    
    def _build_optimal_parlay(self, safe_bets: List[Dict], current_day: int) -> Optional[Dict]:
        """
        Build optimal parlay from safe bets.
        
        Strategy:
        - Days 1-5: Prefer 2-leg parlays (80% each → 64% combined → 1.56x return)
        - Days 6-10: Use 2-3 leg parlays (75-80% per leg)
        - Days 11-14: Can use 3-4 leg parlays if needed
        """
        if not safe_bets:
            return None
        
        # Determine target number of legs based on day
        # RELAXED: Use 75% threshold for all days if we have enough bets
        if current_day <= 5:
            target_legs = 2
            min_leg_prob = 0.75  # Relaxed from 0.80
        elif current_day <= 10:
            target_legs = 3
            min_leg_prob = 0.75
        else:
            target_legs = 3  # Can use 3-4, start with 3
            min_leg_prob = 0.75
        
        # Filter bets by minimum probability
        qualified_bets = [b for b in safe_bets if b['probability'] >= min_leg_prob]
        
        if len(qualified_bets) < target_legs:
            # Try with lower threshold
            min_leg_prob = 0.70
            qualified_bets = [b for b in safe_bets if b['probability'] >= min_leg_prob]
            if len(qualified_bets) < target_legs:
                return None
        
        # Greedy selection: pick highest probability bets, ensuring diversification
        selected_legs = []
        used_players = set()
        used_games = set()
        
        # Sort by probability (highest first)
        qualified_bets.sort(key=lambda x: x['probability'], reverse=True)
        
        for bet in qualified_bets:
            if len(selected_legs) >= target_legs:
                break
            
            # Skip if same player or same game (diversify)
            if bet['player_id'] in used_players:
                continue
            
            # Allow same game but prefer different games
            if bet['game_id'] in used_games and len(selected_legs) < target_legs - 1:
                continue  # Prefer different games, but allow if we need more legs
            
            selected_legs.append(bet)
            used_players.add(bet['player_id'])
            used_games.add(bet['game_id'])
        
        if len(selected_legs) < target_legs:
            # Didn't get enough legs, return what we have if at least 2
            if len(selected_legs) < 2:
                return None
        
        # Calculate combined probability and return multiplier
        combined_probability = 1.0
        for leg in selected_legs:
            combined_probability *= leg['probability']
        
        # Calculate expected return multiplier
        # For probability P, if we win we get 1/P back (on average)
        # But in reality, parlays have better odds, so we use a simpler approximation
        # 2-leg parlay of 80% each: combined 64%, return ~1.56x
        # 3-leg parlay of 75% each: combined 42%, return ~1.95x
        # Approximation: return_multiplier ≈ 1 + (1 - combined_probability) * 0.8
        expected_return_multiplier = 1.0 + (1.0 - combined_probability) * 0.8
        
        # More accurate: use the actual probability to calculate decimal odds
        # Decimal odds = 1 / probability (simplified)
        # For parlays, multiply decimal odds
        decimal_odds = 1.0
        for leg in selected_legs:
            # Simplified: if probability is 0.80, decimal odds are roughly 1.25
            # More accurately: odds reflect the probability
            leg_decimal = 1.0 / leg['probability']
            decimal_odds *= leg_decimal
        
        # Return multiplier is decimal_odds (bet $1, get back $decimal_odds)
        expected_return_multiplier = decimal_odds
        
        # Validate minimum combined probability
        # RELAXED: For 2-leg parlays with 75% each (56.25% combined), allow lower threshold
        # For 3-leg parlays, still require 55% minimum
        min_combined_prob = 0.55 if len(selected_legs) == 2 else 0.50
        if combined_probability < min_combined_prob:
            return None
        
        return {
            'legs': selected_legs,
            'num_legs': len(selected_legs),
            'combined_probability': combined_probability,
            'expected_return_multiplier': expected_return_multiplier,
            'min_leg_probability': min_leg_prob
        }
    
    def _calculate_bet_amount(
        self,
        current_bankroll: Decimal,
        daily_multiplier: float,
        expected_return_multiplier: float
    ) -> Decimal:
        """
        Calculate bet amount to reach daily target.
        
        Formula:
        1. Daily Target = Current Bankroll × daily_multiplier
        2. Needed Profit = Daily Target - Current Bankroll
        3. Expected Profit Rate = expected_return_multiplier - 1
        4. Bet Amount = Needed Profit / Expected Profit Rate
        5. Cap at 70% of bankroll
        """
        # Calculate daily target
        daily_target = current_bankroll * Decimal(str(daily_multiplier))
        
        # Calculate needed profit
        needed_profit = daily_target - current_bankroll
        
        # Calculate expected profit rate
        expected_profit_rate = expected_return_multiplier - 1.0
        
        if expected_profit_rate <= 0:
            return Decimal('0')
        
        # Calculate bet amount
        bet_amount = Decimal(str(needed_profit)) / Decimal(str(expected_profit_rate))
        
        # Apply safety cap (70% of bankroll)
        max_bet = current_bankroll * Decimal(str(self.max_bet_percentage))
        
        # Use minimum of calculated bet and max bet
        bet_amount = min(bet_amount, max_bet)
        
        # Ensure minimum bet
        if bet_amount < self.min_bet_amount:
            return Decimal('0')
        
        return bet_amount.quantize(Decimal('0.01'))  # Round to 2 decimal places
    
    def get_challenge_status(self, challenge_id: int) -> Optional[Dict]:
        """Get current status of a challenge."""
        challenge = self.db.query(PoorMansBetChallenge).filter(
            PoorMansBetChallenge.challenge_id == challenge_id
        ).first()
        
        if not challenge:
            return None
        
        # Get bet history
        days = self.db.query(PoorMansBetDay).filter(
            PoorMansBetDay.challenge_id == challenge_id
        ).order_by(PoorMansBetDay.day_number).all()
        
        # Calculate progress
        progress_percentage = float(
            (challenge.current_bankroll / challenge.target_amount) * 100
        ) if challenge.target_amount > 0 else 0
        
        days_remaining = (challenge.target_date - date.today()).days if challenge.target_date else 0
        
        return {
            'challenge_id': challenge.challenge_id,
            'name': challenge.name,
            'start_amount': float(challenge.start_amount),
            'target_amount': float(challenge.target_amount),
            'current_bankroll': float(challenge.current_bankroll),
            'progress_percentage': progress_percentage,
            'status': challenge.status,
            'current_day': challenge.current_day,
            'days_target': challenge.days_target,
            'days_remaining': days_remaining,
            'start_date': challenge.start_date.isoformat(),
            'target_date': challenge.target_date.isoformat() if challenge.target_date else None,
            'wins': challenge.wins,
            'losses': challenge.losses,
            'total_bets': challenge.total_bets,
            'days': [
                {
                    'day_id': day.day_id,
                    'day_number': day.day_number,
                    'bet_date': day.bet_date.isoformat(),
                    'bet_amount': float(day.bet_amount),
                    'status': day.status,
                    'starting_bankroll': float(day.starting_bankroll),
                    'ending_bankroll': float(day.ending_bankroll) if day.ending_bankroll else None
                }
                for day in days
            ]
        }
    
    def place_bet(
        self,
        challenge_id: int,
        prediction_ids: List[int],
        bet_amount: Decimal,
        game_date: date,
        notes: Optional[str] = None
    ) -> PoorMansBetDay:
        """
        Place a bet for a challenge day.
        
        Creates UserPlay records, a Parlay (if multiple legs), and a PoorMansBetDay record.
        
        Args:
            challenge_id: Challenge ID
            prediction_ids: List of prediction IDs for the bet legs
            bet_amount: Amount to bet
            game_date: Date of the games
            notes: Optional notes
        
        Returns:
            Created PoorMansBetDay record
        """
        challenge = self.db.query(PoorMansBetChallenge).filter(
            PoorMansBetChallenge.challenge_id == challenge_id
        ).first()
        
        if not challenge:
            raise ValueError("Challenge not found")
        
        if challenge.status != 'active':
            raise ValueError("Challenge is not active")
        
        # Verify we have enough bankroll
        if bet_amount > challenge.current_bankroll:
            raise ValueError("Insufficient bankroll")
        
        # Get predictions
        predictions = self.db.query(Prediction).filter(
            Prediction.prediction_id.in_(prediction_ids)
        ).all()
        
        if len(predictions) != len(prediction_ids):
            raise ValueError("One or more predictions not found")
        
        # Create UserPlay records for each leg
        plays = []
        for pred in predictions:
            bet_line = f"Over {pred.safe_line:.1f}"
            
            play = UserPlay(
                player_id=pred.player_id,
                game_id=pred.game_id,
                stat_type=pred.stat_type,
                bet_line=bet_line,
                predicted_min=int(pred.percentile_25) if pred.percentile_25 else None,
                predicted_max=int(pred.percentile_85) if pred.percentile_85 else None,
                likelihood_score=pred.safe_probability,
                status="pending"
            )
            self.db.add(play)
            plays.append(play)
        
        self.db.flush()  # Get play IDs
        
        # Create Parlay if multiple legs
        parlay = None
        play_id = None
        
        if len(plays) > 1:
            # Calculate combined probability
            combined_prob = 1.0
            for play in plays:
                if play.likelihood_score:
                    combined_prob *= play.likelihood_score
            
            # Calculate odds
            if combined_prob > 0:
                decimal_odds = 1.0 / combined_prob
                if decimal_odds < 2.0:
                    total_odds = -100 / (decimal_odds - 1)
                else:
                    total_odds = 100 * (decimal_odds - 1)
            else:
                total_odds = None
            
            parlay = Parlay(
                name=f"Poor Man's Bet Day {challenge.current_day}",
                total_odds=total_odds,
                total_probability=combined_prob,
                total_legs=len(plays),
                legs_hit=0,
                status="pending",
                notes=notes
            )
            self.db.add(parlay)
            self.db.flush()
            
            # Associate plays with parlay
            parlay.plays = plays
            self.db.flush()
        else:
            # Single bet
            play_id = plays[0].play_id
        
        # Calculate expected return
        if parlay and parlay.total_probability:
            expected_return_multiplier = 1.0 / parlay.total_probability
            target_return = bet_amount * Decimal(str(expected_return_multiplier))
        else:
            target_return = None
        
        # Create PoorMansBetDay record
        bet_day = PoorMansBetDay(
            challenge_id=challenge_id,
            day_number=challenge.current_day,
            bet_date=game_date,
            starting_bankroll=challenge.current_bankroll,
            bet_amount=bet_amount,
            target_return=target_return,
            bet_type='parlay' if parlay else 'single',
            parlay_id=parlay.parlay_id if parlay else None,
            play_id=play_id,
            status='pending',
            notes=notes
        )
        self.db.add(bet_day)
        
        # Update challenge: deduct bet amount, increment total_bets
        challenge.current_bankroll -= bet_amount
        challenge.total_bets += 1
        
        self.db.commit()
        self.db.refresh(bet_day)
        
        return bet_day
    
    def resolve_pending_bets(self) -> Dict:
        """
        Resolve all pending Poor Man's Bet bets based on parlay/play status.
        
        This should be called after parlays are evaluated (e.g., after evaluate_all_finished_parlays).
        
        Returns:
            Dict with resolution summary
        """
        from app.models.parlay import Parlay
        from app.models.user_play import UserPlay
        
        # Find all pending bet days
        pending_days = self.db.query(PoorMansBetDay).filter(
            PoorMansBetDay.status == 'pending'
        ).all()
        
        resolved = 0
        hits = 0
        misses = 0
        still_pending = 0
        errors = 0
        
        for bet_day in pending_days:
            try:
                challenge = self.db.query(PoorMansBetChallenge).filter(
                    PoorMansBetChallenge.challenge_id == bet_day.challenge_id
                ).first()
                
                if not challenge or challenge.status != 'active':
                    continue  # Skip if challenge is not active
                
                # Check bet status based on type
                bet_status = None
                actual_return = None
                
                if bet_day.bet_type == 'parlay' and bet_day.parlay_id:
                    # Check parlay status
                    parlay = self.db.query(Parlay).filter(
                        Parlay.parlay_id == bet_day.parlay_id
                    ).first()
                    
                    if parlay:
                        if parlay.status == 'hit':
                            bet_status = 'hit'
                            # Calculate return: bet_amount * return_multiplier
                            if parlay.total_probability and parlay.total_probability > 0:
                                return_multiplier = 1.0 / parlay.total_probability
                                actual_return = float(bet_day.bet_amount) * return_multiplier
                            else:
                                # Fallback: use 1.51x multiplier (daily target)
                                actual_return = float(bet_day.bet_amount) * self.daily_multiplier
                        elif parlay.status == 'miss':
                            bet_status = 'miss'
                            actual_return = 0.0
                
                elif bet_day.bet_type == 'single' and bet_day.play_id:
                    # Check single play status
                    play = self.db.query(UserPlay).filter(
                        UserPlay.play_id == bet_day.play_id
                    ).first()
                    
                    if play:
                        if play.status == 'hit':
                            bet_status = 'hit'
                            # For single bets, use likelihood_score to calculate return
                            if play.likelihood_score and play.likelihood_score > 0:
                                return_multiplier = 1.0 / play.likelihood_score
                                actual_return = float(bet_day.bet_amount) * return_multiplier
                            else:
                                actual_return = float(bet_day.bet_amount) * self.daily_multiplier
                        elif play.status == 'miss':
                            bet_status = 'miss'
                            actual_return = 0.0
                
                # Only update if we got a definitive status
                if bet_status in ['hit', 'miss']:
                    # Check how many other pending bets exist for this day (before updating this one)
                    other_pending_bets = self.db.query(PoorMansBetDay).filter(
                        and_(
                            PoorMansBetDay.challenge_id == challenge_id,
                            PoorMansBetDay.day_number == bet_day.day_number,
                            PoorMansBetDay.day_id != bet_day.day_id,  # Exclude current bet
                            PoorMansBetDay.status == 'pending'
                        )
                    ).count()
                    
                    # Update bet day
                    bet_day.status = bet_status
                    bet_day.actual_return = Decimal(str(actual_return)) if actual_return else Decimal('0')
                    
                    # Update challenge
                    if bet_status == 'hit':
                        # Add winnings to bankroll (actual_return is total return, bet was already deducted)
                        challenge.current_bankroll += Decimal(str(actual_return))
                        bet_day.ending_bankroll = challenge.current_bankroll
                        challenge.wins += 1
                        
                        # Only increment day if this was the last pending bet for the day
                        if other_pending_bets == 0:
                            challenge.current_day += 1
                        
                        # Check if challenge completed (reached target or exceeded days)
                        if challenge.current_bankroll >= challenge.target_amount:
                            challenge.status = 'completed'
                        elif challenge.current_day > challenge.days_target:
                            # Exceeded days but didn't reach target - mark as failed
                            challenge.status = 'failed'
                        
                        hits += 1
                    else:  # miss
                        # Bankroll already deducted when bet was placed, ending bankroll is current bankroll
                        bet_day.ending_bankroll = challenge.current_bankroll
                        challenge.losses += 1
                        challenge.status = 'failed'
                        misses += 1
                    
                    resolved += 1
                else:
                    still_pending += 1
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
                errors += 1
        
        # Commit all changes
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            errors += 1
        
        return {
            'resolved': resolved,
            'hits': hits,
            'misses': misses,
            'still_pending': still_pending,
            'errors': errors
        }

