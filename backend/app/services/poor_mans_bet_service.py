"""
Poor Man's Bet Service

Service for managing Poor Man's Bet challenges - compound small amounts daily using very safe bets.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from typing import Dict, List, Optional, Tuple
from datetime import date, timedelta, timezone
from decimal import Decimal
import math
import random

from app.models.poor_mans_bet import PoorMansBetChallenge, PoorMansBetDay
from app.models.prediction import Prediction
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team
from app.models.parlay import Parlay
from app.models.user_play import UserPlay
from app.services.prediction_history_helper import get_last_n_games_for_stat


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
            game_date: Date to get bets for (if None, calculates based on challenge day)
            allow_multiple: If True, return multiple suggestions for different time slots
        
        Returns:
            Dict with bet suggestion(s) or None if no safe bets available
            If allow_multiple=True, returns dict with 'suggestions' list and 'multiple' flag
        """
        challenge = self.db.query(PoorMansBetChallenge).filter(
            PoorMansBetChallenge.challenge_id == challenge_id
        ).first()
        
        if not challenge:
            return None
        
        if challenge.status != 'active':
            return None
        
        # Calculate target date based on challenge day if not provided
        if game_date is None:
            # Day 1 = start_date, Day 2 = start_date + 1 day, etc.
            days_offset = challenge.current_day - 1
            calculated_date = challenge.start_date + timedelta(days=days_offset)
            
            # If calculated date is in the past, use today instead
            # If calculated date is in the future, that's okay (we can still get suggestions)
            if calculated_date < date.today():
                game_date = date.today()
            else:
                game_date = calculated_date
            
            # Find the next date with games if the calculated date has none
            # Check up to 7 days ahead
            from app.models.game import Game
            original_date = game_date
            check_date = game_date
            max_days_ahead = 7
            days_checked = 0
            
            while days_checked < max_days_ahead:
                games_count = self.db.query(Game).filter(
                    and_(
                        Game.game_date == check_date,
                        Game.game_status.in_(['scheduled', 'in_progress'])
                    )
                ).count()
                
                if games_count > 0:
                    if check_date != original_date:
                        print(f"📅 Challenge Day {challenge.current_day}: No games on {original_date}, using {check_date} instead")
                    game_date = check_date
                    break
                
                check_date += timedelta(days=1)
                days_checked += 1
            else:
                # No games found in next 7 days - use original calculated date anyway
                print(f"⚠️  Challenge Day {challenge.current_day}: No games found in next 7 days from {original_date}, using {original_date}")
        else:
            # Use provided date as-is
            game_date = game_date
        
        print(f"🎯 Challenge Day {challenge.current_day}: Looking for suggestions for {game_date}")
        
        # Get all safe bets for the date
        # Get sport from challenge (default to NBA if not set)
        challenge_sport = getattr(challenge, 'sport', 'NBA')
        all_safe_bets = self._find_safest_bets(game_date, challenge.current_day, sport=challenge_sport)
        
        if not all_safe_bets:
            return None
        
        # Group bets by game time slot if allow_multiple
        if allow_multiple:
            from datetime import datetime, timezone
            from collections import defaultdict
            
            # Group by time slot (early: before 4pm, mid: 4pm-7pm, late: after 7pm)
            time_slots = defaultdict(list)
            bets_without_time = []
            
            for bet in all_safe_bets:
                time_slot = None
                if bet.get('game_time'):
                    try:
                        # Parse game time - handle various formats
                        game_time_str = bet['game_time']
                        if isinstance(game_time_str, str):
                            # Handle different timezone formats
                            if game_time_str.endswith('Z'):
                                game_time_str = game_time_str.replace('Z', '+00:00')
                            elif '+' not in game_time_str and '-' not in game_time_str[-6:]:
                                # No timezone info - assume UTC and convert
                                game_time_str = game_time_str + '+00:00'
                            game_time = datetime.fromisoformat(game_time_str)
                        elif hasattr(game_time_str, 'hour'):
                            # Already a datetime object
                            game_time = game_time_str
                        else:
                            game_time = None
                        
                        if game_time:
                            # Get hour in Eastern time (where most NBA games are scheduled)
                            # NBA games are typically scheduled in Eastern time
                            
                            # If no timezone, assume it's already Eastern time (from database)
                            if game_time.tzinfo is None:
                                hour = game_time.hour
                            else:
                                # Convert to Eastern time (ET is UTC-5, EDT is UTC-4)
                                # For simplicity, use UTC-5 (ET) for classification
                                # Most late games are 7pm+ ET
                                et_tz = timezone(timedelta(hours=-5))
                                try:
                                    game_time_et = game_time.astimezone(et_tz)
                                    hour = game_time_et.hour
                                except:
                                    # If conversion fails, use the hour as-is
                                    hour = game_time.hour
                            
                            # Classify by Eastern time hour (7pm ET = 19:00 = late games)
                            if hour < 16:  # Before 4pm ET
                                time_slot = 'early'
                            elif hour < 19:  # 4pm-6:59pm ET
                                time_slot = 'mid'
                            else:  # 7pm ET and later
                                time_slot = 'late'
                    except Exception as e:
                        # If parsing fails, log but continue - we'll skip this bet
                        import traceback
                        print(f"⚠️ Warning: Failed to parse game_time '{bet.get('game_time')}': {e}")
                        # Don't skip - add to bets without time for fallback
                        bets_without_time.append(bet)
                        continue
                
                # Only append if we successfully determined the time slot
                if time_slot:
                    time_slots[time_slot].append(bet)
                else:
                    # No game time available - add to fallback list
                    bets_without_time.append(bet)
            
            # If no time slots found, use all bets as fallback (no time-based grouping)
            if not any(time_slots.values()) and bets_without_time:
                print(f"⚠️ No game times available - using all {len(bets_without_time)} bets without time grouping")
                # Use all bets without time grouping
                time_slots['all'] = bets_without_time
            elif bets_without_time:
                # Some bets have times, some don't - distribute those without times across slots
                print(f"⚠️ {len(bets_without_time)} bets without game times - distributing evenly")
                # Distribute evenly across early/mid/late if we have slots
                if time_slots:
                    slots_list = list(time_slots.keys())
                    for i, bet in enumerate(bets_without_time):
                        target_slot = slots_list[i % len(slots_list)]
                        time_slots[target_slot].append(bet)
            
            # Debug: log what time slots we found
            print(f"📊 Time slots found: early={len(time_slots.get('early', []))}, mid={len(time_slots.get('mid', []))}, late={len(time_slots.get('late', []))}, all={len(time_slots.get('all', []))}")
            
            # Shuffle bets within each time slot to ensure variation between suggestions
            for slot in time_slots:
                random.shuffle(time_slots[slot])
            
            # Build suggestions for ALL available time slots upfront
            # Don't filter out time slots - show all available options so user can see early, mid, and late games
            suggestions = []
            
            # Check if we're using 'all' slot (no times available)
            if 'all' in time_slots and len(time_slots['all']) >= 2:
                # No game times - just build one suggestion with all bets
                parlay = self._build_optimal_parlay(time_slots['all'], challenge.current_day)
                if parlay:
                    bet_amount = self._calculate_bet_amount(
                        challenge.current_bankroll,
                        self.daily_multiplier,
                        parlay['expected_return_multiplier']
                    )
                    if bet_amount >= self.min_bet_amount:
                        expected_return = bet_amount * Decimal(str(parlay['expected_return_multiplier']))
                        return {
                            'time_slot': None,  # No time slot since times aren't available
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
                            'reasoning': f"All games (times unavailable): {parlay['num_legs']}-leg parlay with {parlay['combined_probability']*100:.1f}% combined probability"
                        }
            
            # Normal time slot grouping
            for time_slot in ['early', 'mid', 'late']:
                if time_slot not in time_slots or len(time_slots[time_slot]) < 2:
                    if time_slot == 'late':
                        print(f"⚠️ Late games not available: {len(time_slots.get('late', []))} bets found (need 2+)")
                    continue
                
                # Get game IDs for this time slot
                time_slot_game_ids = list(set([bet['game_id'] for bet in time_slots[time_slot]]))
                
                # Build optimal parlay for this time slot
                parlay = self._build_optimal_parlay(time_slots[time_slot], challenge.current_day)
                
                if not parlay:
                    continue
                
                # Calculate bet amount (use current bankroll, which may include winnings from earlier bets)
                # For late games after a miss, allow smaller bets if needed
                bet_amount = self._calculate_bet_amount(
                    challenge.current_bankroll,
                    self.daily_multiplier,
                    parlay['expected_return_multiplier']
                )
                
                # If bet amount is too small, try using a larger percentage of bankroll for late games
                if bet_amount < self.min_bet_amount:
                    # For late games, allow using up to 90% of remaining bankroll if needed
                    if time_slot == 'late' and challenge.current_bankroll >= self.min_bet_amount:
                        max_bet = challenge.current_bankroll * Decimal('0.90')
                        if max_bet >= self.min_bet_amount:
                            bet_amount = max_bet
                        else:
                            continue
                    else:
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
            
            # Debug: log what suggestions we built
            print(f"✅ Built {len(suggestions)} suggestions: {[s['time_slot'] for s in suggestions]}")
            
            # Return suggestions (even if just one - this allows late games to show after early/mid misses)
            if len(suggestions) > 1:
                print(f"📤 Returning multiple suggestions: {[s['time_slot'] for s in suggestions]}")
                return {
                    'multiple': True,
                    'suggestions': suggestions,
                    'challenge_id': challenge_id,
                    'day_number': challenge.current_day,
                    'game_date': game_date.isoformat()
                }
            # If only one time slot has bets (e.g., just late games), still return it
            elif len(suggestions) == 1:
                print(f"📤 Returning single suggestion: {suggestions[0]['time_slot']}")
                # Make it clear this is a single suggestion but still usable
                return suggestions[0]
            # If no suggestions, explicitly check for late games with relaxed requirements
            else:
                # Try to find late games specifically with more relaxed bet amount requirements
                if 'late' in time_slots and len(time_slots['late']) >= 2:
                    late_parlay = self._build_optimal_parlay(time_slots['late'], challenge.current_day)
                    if late_parlay and challenge.current_bankroll >= self.min_bet_amount:
                        # Use a percentage of bankroll for late games if calculated amount is too small
                        min_bet_for_late = max(self.min_bet_amount, challenge.current_bankroll * Decimal('0.30'))
                        bet_amount = min(min_bet_for_late, challenge.current_bankroll * Decimal('0.90'))
                        expected_return = bet_amount * Decimal(str(late_parlay['expected_return_multiplier']))
                        
                        return {
                            'time_slot': 'late',
                            'challenge_id': challenge_id,
                            'day_number': challenge.current_day,
                            'game_date': game_date.isoformat(),
                            'current_bankroll': float(challenge.current_bankroll),
                            'bet_amount': float(bet_amount),
                            'expected_return': float(expected_return),
                            'bet_type': 'parlay',
                            'legs': late_parlay['legs'],
                            'combined_probability': late_parlay['combined_probability'],
                            'expected_return_multiplier': late_parlay['expected_return_multiplier'],
                            'reasoning': f"Late games: {late_parlay['num_legs']}-leg parlay with {late_parlay['combined_probability']*100:.1f}% combined probability (relaxed bet amount for late game recovery)"
                        }
        
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
    
    def _find_safest_bets(self, game_date: date, current_day: int, game_ids: Optional[List[int]] = None, sport: str = 'NBA') -> List[Dict]:
        """
        Find the safest bets for a given date (optionally filtered by game IDs).
        
        ENHANCED CRITERIA for maximum reliability:
        - Probability: 75%+ (prefer 80%+)
        - Confidence Level: HIGH only
        - Volatility: LOW (prefer LOW, MEDIUM only if needed)
        - Sample Size: 20+ games (prefer 30+ for highest reliability)
        - Injury Status: Healthy
        - Lineup: Confirmed starter (for upcoming games)
        
        Prioritizes:
        1. Highest sample size (more reliable historical data)
        2. LOW volatility (less variance = more predictable)
        3. Highest probability (safest bets)
        """
        # Get games for the date, filtering by sport
        if game_ids is None:
            games = self.db.query(Game).filter(
                and_(
                    Game.game_date == game_date,
                    Game.sport == sport
                )
            ).all()
            game_ids = [g.game_id for g in games]
        
        if not game_ids:
            return []
        
        # Determine minimum probability based on day
        # Early days: prefer 80%+, later days can use 75%+
        min_probability = 0.80 if current_day <= 5 else 0.75
        
        # ENHANCED: Try to get the best predictions first (higher sample size, LOW volatility)
        # Priority 1: Sample size 30+, LOW volatility, 80%+ probability
        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id.in_(game_ids),
                Prediction.bet_type == 'safe',
                Prediction.stat_type.in_(['points', 'rebounds', 'assists']),
                Prediction.safe_probability >= max(0.80, min_probability),
                Prediction.confidence_level == 'HIGH',
                Prediction.volatility_level == 'LOW',
                Prediction.sample_size >= 30,  # Prefer larger sample sizes
                Prediction.sport == sport  # Filter by sport
            )
        ).order_by(
            desc(Prediction.sample_size),  # Prioritize larger sample sizes
            desc(Prediction.safe_probability)
        ).limit(30).all()
        
        # Priority 2: If not enough, include sample size 20+, LOW volatility
        if len(predictions) < 4:
            more_predictions = self.db.query(Prediction).filter(
                and_(
                    Prediction.game_id.in_(game_ids),
                    Prediction.bet_type == 'safe',
                    Prediction.stat_type.in_(['points', 'rebounds', 'assists']),
                    Prediction.safe_probability >= min_probability,
                    Prediction.confidence_level == 'HIGH',
                    Prediction.volatility_level == 'LOW',
                    Prediction.sample_size >= 20,
                    Prediction.sport == sport  # Filter by sport
                )
            ).order_by(
                desc(Prediction.sample_size),
                desc(Prediction.safe_probability)
            ).limit(30).all()
            
            # Combine and deduplicate
            existing_ids = {p.prediction_id for p in predictions}
            predictions.extend([p for p in more_predictions if p.prediction_id not in existing_ids])
        
        # Priority 3: If still not enough, allow MEDIUM volatility with sample size 20+
        if len(predictions) < 4:
            more_predictions = self.db.query(Prediction).filter(
                and_(
                    Prediction.game_id.in_(game_ids),
                    Prediction.bet_type == 'safe',
                    Prediction.stat_type.in_(['points', 'rebounds', 'assists']),
                    Prediction.safe_probability >= min_probability,
                    Prediction.confidence_level == 'HIGH',
                    Prediction.volatility_level.in_(['LOW', 'MEDIUM']),
                    Prediction.sample_size >= 20,
                    Prediction.sport == sport  # Filter by sport
                )
            ).order_by(
                Prediction.volatility_level,  # LOW before MEDIUM
                desc(Prediction.sample_size),
                desc(Prediction.safe_probability)
            ).limit(30).all()
            
            existing_ids = {p.prediction_id for p in predictions}
            predictions.extend([p for p in more_predictions if p.prediction_id not in existing_ids])
        
        # Priority 4: Final fallback - sample size 15+, allow MEDIUM volatility
        if len(predictions) < 4:
            more_predictions = self.db.query(Prediction).filter(
                and_(
                    Prediction.game_id.in_(game_ids),
                    Prediction.bet_type == 'safe',
                    Prediction.stat_type.in_(['points', 'rebounds', 'assists']),
                    Prediction.safe_probability >= 0.75,  # Minimum threshold
                    Prediction.confidence_level == 'HIGH',
                    Prediction.volatility_level.in_(['LOW', 'MEDIUM']),
                    Prediction.sample_size >= 15,
                    Prediction.sport == sport  # Filter by sport
                )
            ).order_by(
                Prediction.volatility_level,  # LOW before MEDIUM
                desc(Prediction.sample_size),
                desc(Prediction.safe_probability)
            ).limit(30).all()
            
            existing_ids = {p.prediction_id for p in predictions}
            predictions.extend([p for p in more_predictions if p.prediction_id not in existing_ids])
        
        # ENHANCED SORTING: Multi-factor priority
        # 1. LOW volatility first
        # 2. Higher sample size (more reliable)
        # 3. Higher probability (safer)
        predictions = sorted(predictions, key=lambda p: (
            p.volatility_level != 'LOW',  # LOW (False=0) comes first, MEDIUM (True=1) second
            -(p.sample_size or 0),  # Higher sample size first (negative for desc sort)
            -p.safe_probability  # Higher probability first
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
            
            # Get last 3 games for this stat type
            # Use prediction's sport if available, otherwise use sport parameter
            pred_sport = getattr(pred, 'sport', sport)
            historical_data = get_last_n_games_for_stat(
                db=self.db,
                player_id=pred.player_id,
                stat_type=pred.stat_type,
                sport=pred_sport,
                n_games=3,
                exclude_game_id=pred.game_id,
                include_lineup_analysis=False  # Not critical for poor man's bets
            )
            last_3_games = historical_data['games']
            
            safe_bets.append({
                'prediction_id': pred.prediction_id,
                'player_id': pred.player_id,
                'player_name': player.name,
                'player_team': player_team,
                'team_id': player.current_team_id,  # Add team_id for diversification
                'game_id': pred.game_id,
                'stat_type': pred.stat_type,
                'line': pred.safe_line,
                'probability': pred.safe_probability,
                'confidence_level': pred.confidence_level,
                'volatility_level': pred.volatility_level,
                'sample_size': pred.sample_size,  # Add sample_size for scoring
                'game_time': game_time.isoformat() if game_time else None,
                'last_3_games': last_3_games
            })
        
        return safe_bets
    
    def _build_optimal_parlay(self, safe_bets: List[Dict], current_day: int) -> Optional[Dict]:
        """
        Build optimal parlay from safe bets with enhanced diversification and optimization.
        
        ENHANCED STRATEGY:
        - Better diversification: Avoid players from same team (correlated)
        - Consider sample size and volatility when selecting
        - Optimize for maximum combined probability while maintaining safety
        - Multi-factor scoring: probability, sample_size, volatility, diversification
        
        Strategy:
        - Days 1-5: Prefer 2-leg parlays (80% each → 64% combined → 1.56x return)
        - Days 6-10: Use 2-3 leg parlays (75-80% per leg)
        - Days 11-14: Can use 3-4 leg parlays if needed
        """
        if not safe_bets:
            return None
        
        # Determine target number of legs based on day
        if current_day <= 5:
            target_legs = 2
            min_leg_prob = 0.75
        elif current_day <= 10:
            target_legs = 3
            min_leg_prob = 0.75
        else:
            target_legs = 3
            min_leg_prob = 0.75
        
        # Filter bets by minimum probability
        qualified_bets = [b for b in safe_bets if b['probability'] >= min_leg_prob]
        
        if len(qualified_bets) < target_legs:
            # Try with lower threshold
            min_leg_prob = 0.70
            qualified_bets = [b for b in safe_bets if b['probability'] >= min_leg_prob]
            if len(qualified_bets) < target_legs:
                return None
        
        # ENHANCED: Calculate composite score for each bet
        # Score = probability_weight * prob + sample_weight * (sample_size/50) + volatility_bonus
        # This prioritizes: high probability, large sample size, low volatility
        def calculate_bet_score(bet: Dict) -> float:
            prob = bet['probability']
            sample_size = bet.get('sample_size', 15)
            volatility = bet.get('volatility_level', 'MEDIUM')
            
            # Normalize sample size (0-1 scale, assuming max 50 games)
            sample_score = min(sample_size / 50.0, 1.0)
            
            # Volatility bonus: LOW = +0.05, MEDIUM = 0, HIGH = -0.05
            volatility_bonus = 0.05 if volatility == 'LOW' else (0.0 if volatility == 'MEDIUM' else -0.05)
            
            # Weighted score: 70% probability, 20% sample size, 10% volatility
            score = (prob * 0.70) + (sample_score * 0.20) + volatility_bonus
            
            return score
        
        # Score all bets
        for bet in qualified_bets:
            bet['_score'] = calculate_bet_score(bet)
        
        # Sort by composite score (highest first)
        qualified_bets_sorted = sorted(qualified_bets, key=lambda x: x['_score'], reverse=True)
        
        # Add randomization within similar scores for variation
        score_groups = {}
        for bet in qualified_bets_sorted:
            score_key = round(bet['_score'], 3)
            if score_key not in score_groups:
                score_groups[score_key] = []
            score_groups[score_key].append(bet)
        
        # Shuffle within each score group
        for score_key in score_groups:
            random.shuffle(score_groups[score_key])
        
        # Rebuild sorted list
        qualified_bets = []
        for score_key in sorted(score_groups.keys(), reverse=True):
            qualified_bets.extend(score_groups[score_key])
        
        # ENHANCED: Better diversification
        # Track: players, games, teams (avoid same team - correlated)
        selected_legs = []
        used_players = set()
        used_games = set()
        used_teams = set()  # NEW: Track teams to avoid correlation
        
        # Get team IDs for bets (need to look up from player data)
        # We'll get this from the bet data if available, or skip team check if not
        for bet in qualified_bets:
            if len(selected_legs) >= target_legs:
                break
            
            # Skip if same player
            if bet['player_id'] in used_players:
                continue
            
            # ENHANCED: Avoid same team (players on same team are correlated)
            # If bet has team_id, check it
            bet_team_id = bet.get('team_id')
            if bet_team_id and bet_team_id in used_teams:
                # Same team - only allow if we're desperate (need more legs and few options)
                if len(selected_legs) >= target_legs - 1 and len(qualified_bets) - len(selected_legs) < 3:
                    # Allow it if we're close to target and running out of options
                    pass
                else:
                    continue  # Prefer different teams
            
            # ENHANCED: Prefer different games (but allow same game if needed)
            if bet['game_id'] in used_games:
                # Same game - only allow if we need more legs
                if len(selected_legs) < target_legs - 1:
                    continue  # Prefer different games
                # If we're at target_legs - 1, allow same game as last resort
            
            # Add to selection
            selected_legs.append(bet)
            used_players.add(bet['player_id'])
            used_games.add(bet['game_id'])
            if bet_team_id:
                used_teams.add(bet_team_id)
        
        if len(selected_legs) < target_legs:
            # Didn't get enough legs, return what we have if at least 2
            if len(selected_legs) < 2:
                return None
        
        # Calculate combined probability and return multiplier
        combined_probability = 1.0
        for leg in selected_legs:
            combined_probability *= leg['probability']
        
        # Calculate expected return multiplier using decimal odds
        decimal_odds = 1.0
        for leg in selected_legs:
            leg_decimal = 1.0 / leg['probability']
            decimal_odds *= leg_decimal
        
        expected_return_multiplier = decimal_odds
        
        # Validate minimum combined probability
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
    
    def get_all_eligible_plays(self, challenge_id: int, game_date: Optional[date] = None) -> Dict:
        """
        Get all eligible plays for a challenge day.
        
        Returns all safe bets that meet Poor Man's Bet criteria for the given date,
        grouped by game for easy browsing.
        
        Args:
            challenge_id: Challenge ID
            game_date: Date to get plays for (if None, calculates based on challenge day)
        
        Returns:
            Dict with game_date and list of plays grouped by game
        """
        challenge = self.db.query(PoorMansBetChallenge).filter(
            PoorMansBetChallenge.challenge_id == challenge_id
        ).first()
        
        if not challenge:
            raise ValueError("Challenge not found")
        
        if challenge.status != 'active':
            raise ValueError("Challenge is not active")
        
        # Calculate target date based on challenge day if not provided
        if game_date is None:
            days_offset = challenge.current_day - 1
            calculated_date = challenge.start_date + timedelta(days=days_offset)
            
            if calculated_date < date.today():
                game_date = date.today()
            else:
                game_date = calculated_date
            
            # Find the next date with games if the calculated date has none
            challenge_sport = getattr(challenge, 'sport', 'NBA')
            original_date = game_date
            check_date = game_date
            max_days_ahead = 7
            days_checked = 0
            
            while days_checked < max_days_ahead:
                games_count = self.db.query(Game).filter(
                    and_(
                        Game.game_date == check_date,
                        Game.game_status.in_(['scheduled', 'in_progress']),
                        Game.sport == challenge_sport
                    )
                ).count()
                
                if games_count > 0:
                    if check_date != original_date:
                        print(f"📅 Challenge Day {challenge.current_day}: No games on {original_date}, using {check_date} instead")
                    game_date = check_date
                    break
                
                check_date += timedelta(days=1)
                days_checked += 1
            else:
                print(f"⚠️  Challenge Day {challenge.current_day}: No games found in next 7 days from {original_date}, using {original_date}")
        
        # Get challenge sport
        challenge_sport = getattr(challenge, 'sport', 'NBA')
        
        # Get all safe bets for the date
        all_safe_bets = self._find_safest_bets(game_date, challenge.current_day, sport=challenge_sport)
        
        # Group by game
        from collections import defaultdict
        plays_by_game = defaultdict(list)
        
        for bet in all_safe_bets:
            game_id = bet['game_id']
            plays_by_game[game_id].append(bet)
        
        # Format plays grouped by game
        games = self.db.query(Game).filter(Game.game_id.in_(list(plays_by_game.keys()))).all()
        games_dict = {g.game_id: g for g in games}
        
        team_ids = set()
        for game in games:
            team_ids.add(game.home_team_id)
            team_ids.add(game.away_team_id)
        teams = {t.team_id: t for t in self.db.query(Team).filter(Team.team_id.in_(team_ids)).all()}
        
        formatted_plays = []
        for game_id, plays in plays_by_game.items():
            game = games_dict.get(game_id)
            if not game:
                continue
            
            home_team = teams.get(game.home_team_id)
            away_team = teams.get(game.away_team_id)
            
            formatted_plays.append({
                'game_id': game_id,
                'game_date': game.game_date.isoformat() if game.game_date else None,
                'home_team': home_team.name if home_team else f"Team {game.home_team_id}",
                'away_team': away_team.name if away_team else f"Team {game.away_team_id}",
                'home_team_abbr': home_team.abbreviation if home_team else None,
                'away_team_abbr': away_team.abbreviation if away_team else None,
                'game_status': game.game_status,
                'plays': plays
            })
        
        # Sort by game time if available, otherwise by team name
        formatted_plays.sort(key=lambda g: (
            g['plays'][0].get('game_time', ''),
            g['home_team']
        ))
        
        return {
            'game_date': game_date.isoformat(),
            'plays': formatted_plays
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
                        
                        # DO NOT auto-increment day - let user manually advance
                        # User can place multiple bets per day and will click "Next Step" when ready
                        
                        # Check if challenge completed (reached target)
                        if challenge.current_bankroll >= challenge.target_amount:
                            challenge.status = 'completed'
                        # Don't fail on day count - let user decide when to advance
                        
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
    
    def manual_resolve_bet(
        self,
        challenge_id: int,
        day_id: int,
        status: str,
        actual_return: Optional[Decimal] = None
    ) -> Dict:
        """
        Manually resolve a bet day (mark as hit or miss).
        
        Args:
            challenge_id: Challenge ID
            day_id: Day ID to resolve
            status: 'hit' or 'miss'
            actual_return: Optional actual return amount (if not provided, calculated from bet)
        
        Returns:
            Dict with resolution result
        """
        challenge = self.db.query(PoorMansBetChallenge).filter(
            PoorMansBetChallenge.challenge_id == challenge_id
        ).first()
        
        if not challenge:
            raise ValueError("Challenge not found")
        
        if challenge.status != 'active':
            raise ValueError("Challenge is not active")
        
        bet_day = self.db.query(PoorMansBetDay).filter(
            and_(
                PoorMansBetDay.day_id == day_id,
                PoorMansBetDay.challenge_id == challenge_id
            )
        ).first()
        
        if not bet_day:
            raise ValueError("Bet day not found")
        
        if bet_day.status != 'pending':
            raise ValueError(f"Bet day is already {bet_day.status}")
        
        # Calculate actual return if not provided
        if actual_return is None:
            if status == 'hit':
                # Use target return if available, otherwise calculate from probability
                if bet_day.target_return:
                    actual_return = bet_day.target_return
                else:
                    # Fallback: use daily multiplier
                    actual_return = bet_day.bet_amount * Decimal(str(self.daily_multiplier))
            else:  # miss
                actual_return = Decimal('0')
        
        # Update bet day
        bet_day.status = status
        bet_day.actual_return = actual_return
        
        # Update challenge - DON'T auto-increment day, let user manually advance
        if status == 'hit':
            # Add winnings to bankroll (actual_return is total return, bet was already deducted)
            challenge.current_bankroll += actual_return
            bet_day.ending_bankroll = challenge.current_bankroll
            challenge.wins += 1
            
            # DO NOT auto-increment day - allow user to place more bets for same day
            # User will manually click "Next Step" when ready to advance
            
            # Check if challenge completed
            if challenge.current_bankroll >= challenge.target_amount:
                challenge.status = 'completed'
            # Don't fail on day count - let user decide when to advance
        else:  # miss
            # Bankroll already deducted when bet was placed
            bet_day.ending_bankroll = challenge.current_bankroll
            challenge.losses += 1
            
            # Don't immediately fail the challenge - allow late game bets on same day
            # Only fail if bankroll is too low to continue (< $1)
            if challenge.current_bankroll < Decimal('1.00'):
                challenge.status = 'failed'
            # Otherwise, keep challenge active to allow late game bets
            # DO NOT auto-increment day on miss - user can try late games
        
        self.db.commit()
        
        return {
            'updated_bankroll': challenge.current_bankroll,
            'challenge_status': challenge.status,
            'new_day': challenge.current_day
        }
    
    def advance_to_next_day(self, challenge_id: int, final_bankroll: Optional[float] = None) -> Dict:
        """
        Manually advance challenge to the next day, optionally updating final bankroll.
        
        This is useful when you want to skip a day or manually progress.
        Can also be used to update the bankroll if manual adjustments are needed.
        
        Args:
            challenge_id: Challenge ID
            final_bankroll: Optional final bankroll amount to set before advancing
        
        Returns:
            Dict with new day info
        """
        challenge = self.db.query(PoorMansBetChallenge).filter(
            PoorMansBetChallenge.challenge_id == challenge_id
        ).first()
        
        if not challenge:
            raise ValueError("Challenge not found")
        
        if challenge.status != 'active':
            raise ValueError("Challenge is not active")
        
        # Update bankroll if provided
        if final_bankroll is not None:
            if final_bankroll < 0:
                raise ValueError("Bankroll cannot be negative")
            challenge.current_bankroll = Decimal(str(final_bankroll))
            print(f"💰 Updated bankroll to ${final_bankroll:.2f} before advancing to next day")
        
        # Check if there are any pending bets for the current day
        pending_bets = self.db.query(PoorMansBetDay).filter(
            and_(
                PoorMansBetDay.challenge_id == challenge_id,
                PoorMansBetDay.day_number == challenge.current_day,
                PoorMansBetDay.status == 'pending'
            )
        ).count()
        
        if pending_bets > 0:
            print(f"⚠️  Warning: {pending_bets} pending bet(s) for day {challenge.current_day}, advancing anyway")
        
        # Advance to next day
        challenge.current_day += 1
        
        # Check if exceeded days target
        if challenge.current_day > challenge.days_target:
            if challenge.current_bankroll < challenge.target_amount:
                challenge.status = 'failed'
            else:
                challenge.status = 'completed'
        
        self.db.commit()
        
        return {
            'new_day': challenge.current_day,
            'current_bankroll': float(challenge.current_bankroll),
            'challenge_status': challenge.status
        }

