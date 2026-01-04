"""
Bankroll Recommendation Service

Analyzes user's bankroll and recommends optimal betting strategies with specific plays and dollar allocations.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Dict, List, Optional
from datetime import date
from decimal import Decimal
from app.services.builder_plays import BuilderPlaysService
from app.services.suggested_bets import SuggestedBetsService
from app.services.poor_mans_bet_service import PoorMansBetService
from app.models.prediction import Prediction
from app.models.game import Game


class BankrollRecommendationService:
    """Generate bankroll-based betting recommendations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.builder_service = BuilderPlaysService(db)
        self.suggested_service = SuggestedBetsService(db)
        self.pmb_service = PoorMansBetService(db)
    
    def get_recommendations(
        self,
        total_bankroll: float,
        reserve_amount: float,
        game_date: Optional[date] = None,
        risk_tolerance: str = "moderate"  # conservative, moderate, aggressive
    ) -> Dict:
        """
        Get betting recommendations based on bankroll.
        
        Args:
            total_bankroll: Total amount available
            reserve_amount: Amount to reserve/save
            game_date: Date to get recommendations for (default: today)
            risk_tolerance: Risk tolerance level (conservative, moderate, aggressive)
        
        Returns:
            Dict with available_to_bet and recommendations list
        """
        if game_date is None:
            game_date = date.today()
        
        available_to_bet = Decimal(str(total_bankroll)) - Decimal(str(reserve_amount))
        
        if available_to_bet <= 0:
            return {
                "available_to_bet": float(available_to_bet),
                "recommendations": [],
                "message": "No money available to bet after reserves."
            }
        
        recommendations = []
        
        # Strategy 1: Poor Man's Bet Challenge (for small amounts, aggressive growth)
        if available_to_bet >= 1 and available_to_bet <= 10 and risk_tolerance in ["moderate", "aggressive"]:
            pmb_rec = self._generate_poor_mans_bet_recommendation(available_to_bet)
            if pmb_rec:
                recommendations.append(pmb_rec)
        
        # Strategy 2: Builder Plays (moderate amounts, steady growth)
        if available_to_bet >= 5:
            builder_recs = self._generate_builder_play_recommendations(
                available_to_bet, game_date, risk_tolerance
            )
            recommendations.extend(builder_recs)
        
        # Strategy 3: Safe Long Parlays (larger amounts, lottery-style)
        if available_to_bet >= 50 and risk_tolerance in ["moderate", "aggressive"]:
            long_parlay_recs = self._generate_safe_long_parlay_recommendations(
                available_to_bet, game_date, risk_tolerance
            )
            recommendations.extend(long_parlay_recs)
        
        # Strategy 4: Individual Safe Bets (any amount, capital preservation)
        if available_to_bet >= 10 and risk_tolerance == "conservative":
            safe_bet_recs = self._generate_safe_bet_recommendations(
                available_to_bet, game_date
            )
            recommendations.extend(safe_bet_recs)
        
        # Strategy 5: Mixed Strategy (larger amounts, balanced approach)
        if available_to_bet >= 50:
            mixed_rec = self._generate_mixed_strategy_recommendation(
                available_to_bet, game_date, risk_tolerance
            )
            if mixed_rec:
                recommendations.append(mixed_rec)
        
        # Sort recommendations by priority score (higher is better)
        for rec in recommendations:
            rec['priority_score'] = self._calculate_priority_score(
                rec, available_to_bet, risk_tolerance
            )
        
        recommendations.sort(key=lambda x: x['priority_score'], reverse=True)
        
        # Assign priority numbers
        for idx, rec in enumerate(recommendations, 1):
            rec['priority'] = idx
        
        return {
            "available_to_bet": float(available_to_bet),
            "total_bankroll": float(total_bankroll),
            "reserve_amount": float(reserve_amount),
            "risk_tolerance": risk_tolerance,
            "game_date": game_date.isoformat(),
            "recommendations": recommendations
        }
    
    def _generate_poor_mans_bet_recommendation(self, available_amount: Decimal) -> Optional[Dict]:
        """Generate Poor Man's Bet challenge recommendation."""
        # Suggest using 20-50% of available for PMB challenge
        suggested_amount = min(available_amount, Decimal('5.00'))
        if suggested_amount < Decimal('1.00'):
            return None
        
        # Calculate target and days (same logic as PMB service)
        target_amount = suggested_amount * Decimal('200')  # 200x growth
        days_target = 14
        
        return {
            "strategy": "poor_mans_bet",
            "allocation": float(suggested_amount),
            "reasoning": f"Start a Poor Man's Bet challenge with ${suggested_amount:.2f}. Can grow to ${target_amount:.2f} in {days_target} days if successful. High risk, high reward.",
            "challenge_config": {
                "start_amount": float(suggested_amount),
                "target_amount": float(target_amount),
                "days_target": days_target
            },
            "suggested_bets": []  # PMB bets are generated daily, not here
        }
    
    def _generate_builder_play_recommendations(
        self, available_amount: Decimal, game_date: date, risk_tolerance: str
    ) -> List[Dict]:
        """Generate builder play recommendations with money allocation."""
        # Get builder plays
        builder_plays = self.builder_service.get_builder_plays(
            game_date=game_date,
            limit=10,  # Get more options
            num_legs=2 if risk_tolerance == "conservative" else 3
        )
        
        if not builder_plays:
            return []
        
        # Select best builder plays (top 3-5)
        max_bets = 5 if available_amount >= 50 else 3
        selected_plays = builder_plays[:max_bets]
        
        # Allocate money using probability + ROI mix
        allocations = self._allocate_money_by_probability_roi(
            selected_plays, available_amount, strategy_type="builder"
        )
        
        if not allocations:
            return []
        
        recommendation = {
            "strategy": "builder",
            "allocation": float(sum(alloc['amount'] for alloc in allocations)),
            "reasoning": f"Builder plays are perfect for steady growth. {len(allocations)} suggested parlays with 75%+ combined probability each, designed to roughly double your money.",
            "suggested_bets": allocations
        }
        
        return [recommendation]
    
    def _generate_safe_long_parlay_recommendations(
        self, available_amount: Decimal, game_date: date, risk_tolerance: str
    ) -> List[Dict]:
        """Generate safe long parlay recommendations."""
        # Allocate 10-20% of available for long parlays
        allocation_pct = 0.15 if risk_tolerance == "aggressive" else 0.10
        parlay_budget = available_amount * Decimal(str(allocation_pct))
        
        if parlay_budget < Decimal('5.00'):
            return []
        
        # Get safe long parlays
        long_parlays = self.suggested_service.get_safe_long_parlays(
            game_date=game_date,
            limit=2,  # Just 1-2 long parlays
            num_legs=12,
            min_leg_probability=0.75
        )
        
        if not long_parlays:
            return []
        
        # Split budget across long parlays
        allocations = []
        num_parlays = min(len(long_parlays), 2)
        per_parlay = parlay_budget / Decimal(str(num_parlays))
        
        for parlay in long_parlays[:num_parlays]:
            combined_prob = parlay['combined_probability']
            if combined_prob > 0:
                decimal_odds = 1.0 / combined_prob
                expected_return = float(per_parlay) * decimal_odds
                
                allocations.append({
                    "bet_type": "safe_long_parlay",
                    "amount": float(per_parlay),
                    "parlay_legs": parlay['legs'],
                    "num_legs": parlay['num_legs'],
                    "combined_probability": combined_prob,
                    "expected_return": round(expected_return, 2),
                    "odds_display": parlay.get('odds_display', 'N/A')
                })
        
        if not allocations:
            return []
        
        return [{
            "strategy": "safe_long_parlay",
            "allocation": float(sum(a['amount'] for a in allocations)),
            "reasoning": f"Safe long parlays are lottery-style bets with high potential returns. {len(allocations)} suggested parlays with 12+ legs each, combining very safe individual bets for big odds.",
            "suggested_bets": allocations
        }]
    
    def _generate_safe_bet_recommendations(
        self, available_amount: Decimal, game_date: date
    ) -> List[Dict]:
        """Generate individual safe bet recommendations."""
        # Get top safe bets
        safe_bets = self.suggested_service.get_suggested_bets(
            game_date=game_date,
            limit=10,
            min_probability=0.75,
            include_long_shots=False
        )
        
        # Filter to only safe bets
        safe_bets = [b for b in safe_bets if b.get('bet_type') == 'safe']
        
        if not safe_bets:
            return []
        
        # Select top 5-8 safe bets
        selected_bets = safe_bets[:min(8, len(safe_bets))]
        
        # Allocate money by probability + ROI
        allocations = self._allocate_money_by_probability_roi(
            selected_bets, available_amount, strategy_type="safe_bet"
        )
        
        if not allocations:
            return []
        
        return [{
            "strategy": "safe_bets",
            "allocation": float(sum(a['amount'] for a in allocations)),
            "reasoning": f"Individual safe bets preserve capital with low risk. {len(allocations)} suggested bets with 75%+ probability each, providing steady but smaller returns.",
            "suggested_bets": allocations
        }]
    
    def _generate_mixed_strategy_recommendation(
        self, available_amount: Decimal, game_date: date, risk_tolerance: str
    ) -> Optional[Dict]:
        """Generate mixed strategy recommendation."""
        # Allocation percentages based on risk tolerance
        if risk_tolerance == "conservative":
            builder_pct = 0.70
            long_parlay_pct = 0.10
            safe_bet_pct = 0.20
        elif risk_tolerance == "aggressive":
            builder_pct = 0.50
            long_parlay_pct = 0.30
            safe_bet_pct = 0.20
        else:  # moderate
            builder_pct = 0.60
            long_parlay_pct = 0.20
            safe_bet_pct = 0.20
        
        builder_budget = available_amount * Decimal(str(builder_pct))
        long_parlay_budget = available_amount * Decimal(str(long_parlay_pct))
        safe_bet_budget = available_amount * Decimal(str(safe_bet_pct))
        
        all_bets = []
        
        # Get builder plays
        if builder_budget >= Decimal('5.00'):
            builder_plays = self.builder_service.get_builder_plays(
                game_date=game_date, limit=5, num_legs=2
            )
            if builder_plays:
                builder_allocations = self._allocate_money_by_probability_roi(
                    builder_plays, builder_budget, strategy_type="builder"
                )
                all_bets.extend(builder_allocations)
        
        # Get long parlays
        if long_parlay_budget >= Decimal('5.00') and risk_tolerance != "conservative":
            long_parlays = self.suggested_service.get_safe_long_parlays(
                game_date=game_date, limit=1, num_legs=12, min_leg_probability=0.75
            )
            if long_parlays:
                parlay = long_parlays[0]
                combined_prob = parlay['combined_probability']
                if combined_prob > 0:
                    decimal_odds = 1.0 / combined_prob
                    expected_return = float(long_parlay_budget) * decimal_odds
                    all_bets.append({
                        "bet_type": "safe_long_parlay",
                        "amount": float(long_parlay_budget),
                        "parlay_legs": parlay['legs'],
                        "num_legs": parlay['num_legs'],
                        "combined_probability": combined_prob,
                        "expected_return": round(expected_return, 2),
                        "odds_display": parlay.get('odds_display', 'N/A')
                    })
        
        # Get safe bets
        if safe_bet_budget >= Decimal('5.00'):
            safe_bets = self.suggested_service.get_suggested_bets(
                game_date=game_date, limit=5, min_probability=0.75, include_long_shots=False
            )
            safe_bets = [b for b in safe_bets if b.get('bet_type') == 'safe']
            if safe_bets:
                safe_allocations = self._allocate_money_by_probability_roi(
                    safe_bets, safe_bet_budget, strategy_type="safe_bet"
                )
                all_bets.extend(safe_allocations)
        
        if not all_bets:
            return None
        
        return {
            "strategy": "mixed",
            "allocation": float(sum(b['amount'] for b in all_bets)),
            "reasoning": f"Mixed strategy diversifies risk across {len(all_bets)} bets: builder plays for steady growth, long parlays for big potential, and safe bets as a hedge. Balanced approach for {risk_tolerance} risk tolerance.",
            "suggested_bets": all_bets
        }
    
    def _allocate_money_by_probability_roi(
        self, bets: List[Dict], total_amount: Decimal, strategy_type: str
    ) -> List[Dict]:
        """
        Allocate money across bets using a mix of probability and ROI.
        
        For each bet, calculate a score: (probability * weight) + (roi * weight)
        Then allocate proportionally based on scores.
        """
        if not bets:
            return []
        
        # Calculate scores for each bet
        scored_bets = []
        for bet in bets:
            # Extract probability
            if strategy_type == "builder":
                prob = bet.get('combined_probability', 0)
                # Calculate ROI (expected return / bet amount)
                # For builder plays, assume ~2x return (odds around -110 to -150)
                # Decimal odds ≈ 1 / prob, so ROI = (decimal_odds - 1)
                if prob > 0:
                    decimal_odds = 1.0 / prob
                    roi = decimal_odds - 1.0
                else:
                    roi = 0
            elif strategy_type == "safe_long_parlay":
                prob = bet.get('combined_probability', 0)
                if prob > 0:
                    decimal_odds = 1.0 / prob
                    roi = decimal_odds - 1.0
                else:
                    roi = 0
            else:  # safe_bet
                prob = bet.get('probability', 0)
                # Safe bets have lower ROI (~0.3x for 75% probability)
                if prob > 0:
                    decimal_odds = 1.0 / prob
                    roi = decimal_odds - 1.0
                else:
                    roi = 0
            
            # Score = 60% probability + 40% ROI (weighted)
            prob_score = prob * 0.6
            roi_score = min(roi, 2.0) / 2.0 * 0.4  # Normalize ROI (cap at 2.0 for safety)
            total_score = prob_score + roi_score
            
            scored_bets.append({
                'bet': bet,
                'probability': prob,
                'roi': roi,
                'score': total_score
            })
        
        # Calculate total score
        total_score = sum(b['score'] for b in scored_bets)
        if total_score == 0:
            # Fallback: equal allocation
            per_bet = total_amount / Decimal(str(len(bets)))
            allocations = []
            for bet in bets:
                allocations.append({
                    "bet_type": "builder" if strategy_type == "builder" else "safe_long_parlay" if strategy_type == "safe_long_parlay" else "safe_bet",
                    "amount": float(per_bet),
                    **self._format_bet_for_response(bet, strategy_type)
                })
            return allocations
        
        # Allocate proportionally
        allocations = []
        min_bet = Decimal('1.00')  # Minimum $1 per bet
        
        for scored in scored_bets:
            if total_score > 0:
                allocation_pct = scored['score'] / total_score
                amount = total_amount * Decimal(str(allocation_pct))
                amount = max(amount, min_bet)  # Ensure minimum
            else:
                amount = total_amount / Decimal(str(len(scored_bets)))
            
            bet_data = self._format_bet_for_response(scored['bet'], strategy_type)
            
            # Calculate expected return
            if strategy_type == "builder" or strategy_type == "safe_long_parlay":
                combined_prob = bet_data.get('combined_probability', 0)
                if combined_prob > 0:
                    expected_return = float(amount) * (1.0 / combined_prob)
                else:
                    expected_return = 0
            else:  # safe_bet
                prob = scored['probability']
                if prob > 0:
                    expected_return = float(amount) * (1.0 / prob)
                else:
                    expected_return = 0
            
            allocations.append({
                "bet_type": "builder" if strategy_type == "builder" else "safe_long_parlay" if strategy_type == "safe_long_parlay" else "safe_bet",
                "amount": float(amount),
                "probability": float(scored['probability']),
                "expected_roi": float(scored['roi']),
                "expected_return": round(expected_return, 2),
                **bet_data
            })
        
        # Round allocations and adjust for rounding errors
        total_allocated = sum(Decimal(str(a['amount'])) for a in allocations)
        if total_allocated > total_amount:
            # Scale down proportionally
            scale = total_amount / total_allocated
            for alloc in allocations:
                alloc['amount'] = float(Decimal(str(alloc['amount'])) * scale)
        elif total_allocated < total_amount:
            # Add remainder to highest score bet
            remainder = total_amount - total_allocated
            if allocations:
                allocations[0]['amount'] += float(remainder)
        
        return allocations
    
    def _format_bet_for_response(self, bet: Dict, strategy_type: str) -> Dict:
        """Format bet data for API response."""
        # Note: amount will be added later in the allocation method
        if strategy_type == "builder":
            return {
                "parlay_legs": bet.get('legs', []),
                "num_legs": bet.get('num_legs', 0),
                "combined_probability": bet.get('combined_probability', 0),
                "odds_display": bet.get('odds_display', 'N/A')
            }
        elif strategy_type == "safe_long_parlay":
            return {
                "parlay_legs": bet.get('legs', []),
                "num_legs": bet.get('num_legs', 0),
                "combined_probability": bet.get('combined_probability', 0),
                "odds_display": bet.get('odds_display', 'N/A')
            }
        else:  # safe_bet
            stat_type = bet.get('stat_type', '').lower()
            stat_abbrev = {
                'points': 'PTS',
                'rebounds': 'REB',
                'assists': 'AST'
            }.get(stat_type, stat_type.upper() if stat_type else 'STAT')
            line = bet.get('line', 0)
            return {
                "prediction_id": bet.get('prediction_id'),
                "player_id": bet.get('player_id'),
                "player_name": bet.get('player_name'),
                "player_team": bet.get('player_team'),
                "game_id": bet.get('game_id'),
                "stat_type": bet.get('stat_type'),
                "line": line,
                "bet_line": f"{stat_abbrev} Over {line:.1f}"
            }
    
    def _calculate_priority_score(
        self, recommendation: Dict, available_amount: Decimal, risk_tolerance: str
    ) -> float:
        """Calculate priority score for ranking recommendations."""
        score = 0.0
        
        strategy = recommendation.get('strategy')
        allocation = Decimal(str(recommendation.get('allocation', 0)))
        suggested_bets = recommendation.get('suggested_bets', [])
        
        # Strategy-specific base scores
        if strategy == "poor_mans_bet":
            score += 50 if risk_tolerance in ["moderate", "aggressive"] else 20
        elif strategy == "builder":
            score += 80 if risk_tolerance == "moderate" else 70
        elif strategy == "safe_long_parlay":
            score += 60 if risk_tolerance == "aggressive" else 40
        elif strategy == "safe_bets":
            score += 90 if risk_tolerance == "conservative" else 50
        elif strategy == "mixed":
            score += 75
        
        # Bonus for number of bets (diversification)
        if len(suggested_bets) > 1:
            score += min(len(suggested_bets) * 2, 20)
        
        # Bonus/penalty for allocation size relative to available
        allocation_pct = float(allocation / available_amount) if available_amount > 0 else 0
        if 0.3 <= allocation_pct <= 0.8:  # Sweet spot
            score += 10
        elif allocation_pct > 0.95:  # Too much allocated
            score -= 10
        
        # Bonus for high probability bets
        if suggested_bets:
            avg_prob = sum(b.get('probability', b.get('combined_probability', 0)) for b in suggested_bets) / len(suggested_bets)
            if avg_prob > 0.75:
                score += 15
            elif avg_prob > 0.65:
                score += 10
        
        return score

