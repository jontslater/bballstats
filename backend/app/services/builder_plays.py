"""
Builder Plays Service

Generates safe parlays designed to roughly double the money (odds around -110 to -150).
Target: Bet $10, win $8-9 (total return $18-19).
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from typing import List, Dict, Optional
from datetime import date, timedelta
from app.models.prediction import Prediction
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team
from itertools import combinations
import random


class BuilderPlaysService:
    """Generate builder plays - safe parlays to double money."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_builder_plays(
        self,
        game_date: Optional[date] = None,
        limit: int = 5,
        target_odds_range: tuple = (-150, -110),  # Target odds range
        min_leg_probability: float = 0.75,  # Each leg should be 75%+ likely
        num_legs: int = 2,  # 2 or 3 legs
        exclude_player_ids: Optional[List[int]] = None  # Player IDs to exclude from generation
    ) -> List[Dict]:
        """
        Get builder plays - safe parlays designed to double money.
        
        Args:
            game_date: Date to get suggestions for (default: today)
            limit: Maximum number of builder plays
            target_odds_range: Target odds range (min, max) in American format
            min_leg_probability: Minimum probability for each leg (default 0.75 = 75%)
            num_legs: Number of legs in parlay (2 or 3)
        
        Returns:
            List of builder play dictionaries
        """
        if game_date is None:
            game_date = date.today()
        
        # Get games for the date (include finished games for historical viewing)
        games = self.db.query(Game).filter(
            Game.game_date == game_date
        ).all()
        
        if not games:
            return []
        
        game_ids = [g.game_id for g in games]
        
        # Get very safe predictions (75%+ probability)
        # Use safe_line with safe_probability >= min_leg_probability
        # Try with 75% first, but if not enough, lower to 70%
        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id.in_(game_ids),
                Prediction.bet_type == 'safe',
                Prediction.stat_type.in_(['points', 'rebounds', 'assists']),
                Prediction.safe_probability >= min_leg_probability,
                Prediction.confidence_level.in_(['HIGH', 'MEDIUM']),
                Prediction.pass_reason.is_(None)  # Only valid predictions
            )
        ).order_by(desc(Prediction.safe_probability)).all()
        
        # Filter out injured players
        from app.services.injury_context import InjuryContext
        injury_context = InjuryContext(self.db)
        healthy_predictions = []
        for pred in predictions:
            injury_status = injury_context.get_player_injury_status(pred.player_id)
            if injury_status and injury_status['status'] in ['Out', 'Doubtful', 'Questionable']:
                continue  # Skip injured players
            healthy_predictions.append(pred)
        predictions = healthy_predictions
        
        # Debug: Log how many predictions we found
        print(f"[Builder Plays] Found {len(predictions)} safe predictions (≥{min_leg_probability*100}%) for {len(games)} games")
        
        # If not enough with 75%, try 70%
        if len(predictions) < num_legs and min_leg_probability >= 0.75:
            print(f"[Builder Plays] Not enough with 75% threshold, trying 70%...")
            predictions = self.db.query(Prediction).filter(
                and_(
                    Prediction.game_id.in_(game_ids),
                    Prediction.bet_type == 'safe',
                    Prediction.stat_type.in_(['points', 'rebounds', 'assists']),
                    Prediction.safe_probability >= 0.70,  # Lower threshold
                    Prediction.confidence_level.in_(['HIGH', 'MEDIUM']),
                    Prediction.pass_reason.is_(None)
                )
            ).order_by(desc(Prediction.safe_probability)).all()
            
            # Filter out injured players again
            healthy_predictions = []
            for pred in predictions:
                injury_status = injury_context.get_player_injury_status(pred.player_id)
                if injury_status and injury_status['status'] in ['Out', 'Doubtful', 'Questionable']:
                    continue  # Skip injured players
                healthy_predictions.append(pred)
            predictions = healthy_predictions
            # print(f"[Builder Plays] Found {len(predictions)} safe predictions with 70% threshold")
        
        if len(predictions) < num_legs:
            # print(f"[Builder Plays] Not enough predictions ({len(predictions)} < {num_legs} legs required)")
            return []
        
        # Generate builder plays
        builder_plays = []
        used_players = set()
        used_games = set()
        
        # Try to create parlays - use simpler approach, less strict on diversification
        attempts = 0
        max_attempts = limit * 30  # Try many combinations
        
        while len(builder_plays) < limit and attempts < max_attempts:
            attempts += 1
            
            # Select legs - prefer different players but be flexible
            selected_predictions = []
            temp_used_players = set()
            
            # Shuffle to get variety, but exclude specified players
            exclude_set = set(exclude_player_ids) if exclude_player_ids else set()
            available_preds = [p for p in predictions if p.player_id not in exclude_set]
            random.shuffle(available_preds)
            
            for pred in available_preds:
                if len(selected_predictions) >= num_legs:
                    break
                
                # Skip if we already have this prediction (shouldn't happen, but safety check)
                if pred in selected_predictions:
                    continue
                
                # Prefer different players, but allow if we're running out of options
                if pred.player_id in temp_used_players:
                    # Only skip if we have enough other options
                    if len(selected_predictions) < num_legs - 1:
                        continue  # Skip duplicate player if we still need more legs
                    # Otherwise allow it if it's the last leg we need
                
                selected_predictions.append(pred)
                temp_used_players.add(pred.player_id)
            
            if len(selected_predictions) < num_legs:
                continue  # Not enough predictions
            
            # Calculate combined probability and odds
            combined_prob = 1.0
            legs_data = []
            
            # Batch load all players, games, and teams to avoid N+1 queries
            player_ids = [p.player_id for p in selected_predictions]
            game_ids = [p.game_id for p in selected_predictions]
            
            players_dict = {p.player_id: p for p in self.db.query(Player).filter(Player.player_id.in_(player_ids)).all()}
            games_dict = {g.game_id: g for g in self.db.query(Game).filter(Game.game_id.in_(game_ids)).all()}
            
            # Get all unique team IDs
            team_ids = set()
            for player in players_dict.values():
                if player.current_team_id:
                    team_ids.add(player.current_team_id)
            for game in games_dict.values():
                if game.home_team_id:
                    team_ids.add(game.home_team_id)
                if game.away_team_id:
                    team_ids.add(game.away_team_id)
            
            teams_dict = {t.team_id: t for t in self.db.query(Team).filter(Team.team_id.in_(list(team_ids))).all()} if team_ids else {}
            
            for pred in selected_predictions:
                player = players_dict.get(pred.player_id)
                game = games_dict.get(pred.game_id)
                
                if not player or not game:
                    continue
                
                prob = pred.safe_probability
                combined_prob *= prob
                
                # Get player's team
                player_team = None
                if player.current_team_id:
                    team = teams_dict.get(player.current_team_id)
                    player_team = team.abbreviation if team else None
                
                # Get opponent
                if game.home_team_id == player.current_team_id:
                    opponent_team = teams_dict.get(game.away_team_id)
                else:
                    opponent_team = teams_dict.get(game.home_team_id)
                
                opponent = opponent_team.abbreviation if opponent_team else "Unknown"
                
                legs_data.append({
                    "prediction_id": pred.prediction_id,
                    "player_id": pred.player_id,
                    "player_name": player.name,
                    "player_team": player_team,
                    "game_id": pred.game_id,
                    "opponent": opponent,
                    "stat_type": pred.stat_type,
                    "bet_line": f"Over {pred.safe_line:.1f}",
                    "probability": round(prob, 3),
                    "line": round(pred.safe_line, 1)
                })
            
            if len(legs_data) < num_legs:
                continue
            
            # Calculate American odds from probability
            # Correct formula: decimal_odds = 1 / prob
            # For decimal < 2 (prob > 0.5): american_odds = -100 / (decimal - 1)
            # For decimal >= 2 (prob <= 0.5): american_odds = 100 * (decimal - 1)
            if combined_prob > 0:
                decimal_odds = 1.0 / combined_prob
                if decimal_odds < 2.0:  # Probability > 50%
                    american_odds = -100 / (decimal_odds - 1)
                else:  # Probability <= 50%
                    american_odds = 100 * (decimal_odds - 1)
            else:
                continue
            
            # Check if odds are in target range (for builder plays, we want -150 to -110)
            # This corresponds to roughly 60% to 52.4% probability
            # But let's be more flexible - allow up to -200 (66.7% prob) for very safe plays
            expanded_range = (max(target_odds_range[0], -200), target_odds_range[1])
            if not (expanded_range[0] <= american_odds <= expanded_range[1]):
                # Skip if not in target range (commented out debug logging)
                continue
            
            # Format odds
            if american_odds >= 0:
                odds_display = f"+{int(round(american_odds))}"
            else:
                odds_display = f"{int(round(american_odds))}"
            
            # Calculate payout example ($10 bet)
            if american_odds < 0:
                payout = abs(american_odds) / 100 * 10  # For negative odds
            else:
                payout = american_odds / 100 * 10  # For positive odds
            
            total_return = 10 + payout
            
            builder_plays.append({
                "num_legs": num_legs,
                "combined_probability": round(combined_prob, 4),
                "combined_odds": american_odds,
                "odds_display": odds_display,
                "payout_example": {
                    "bet_amount": 10,
                    "win_amount": round(payout, 2),
                    "total_return": round(total_return, 2)
                },
                "legs": legs_data,
                "description": f"{num_legs}-leg builder play - Bet $10 to win ${round(payout, 2)}"
            })
            
            # Debug logging (commented out for production)
            # print(f"[Builder Plays] Created parlay #{len(builder_plays)}: {num_legs} legs, {combined_prob*100:.1f}% prob, {odds_display} odds")
            
            # Mark players as used to avoid duplicates
            for pred in selected_predictions:
                used_players.add(pred.player_id)
        
        # Sort by combined probability (higher is better for builder plays)
        builder_plays.sort(key=lambda x: x['combined_probability'], reverse=True)
        
        return builder_plays[:limit]

