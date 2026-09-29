"""
Suggested Bets Service

Generates suggested bets and parlays based on prediction quality and confidence.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from typing import List, Dict, Optional
from datetime import date, timedelta
from app.models.prediction import Prediction
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team
from app.services.prediction_history_helper import get_last_n_games_for_stat
from app.services.base_sport_service import BaseSportService
from itertools import combinations


class SuggestedBetsService(BaseSportService):
    """Generate suggested bets and parlays."""

    def __init__(self, db: Session, sport: str = 'NBA'):
        super().__init__(db, sport)
    
    def get_suggested_bets(
        self,
        game_date: Optional[date] = None,
        limit: int = 10,
        min_probability: float = 0.60,
        include_long_shots: bool = True
    ) -> List[Dict]:
        """
        Get suggested bets ranked by quality.
        
        Args:
            game_date: Date to get suggestions for (default: today)
            limit: Maximum number of suggestions
            min_probability: Minimum probability threshold for safe bets
        
        Returns:
            List of suggested bet dictionaries
        """
        if game_date is None:
            game_date = date.today()
            print(f"No date provided, using today: {game_date}")

        # Get predictions for the date that are recommended (not 'pass')
        # Include finished games for historical viewing
        games = self.db.query(Game).filter(
            Game.game_date == game_date,
            Game.sport == self.sport
        ).all()

        # If no games found for exact date, try a broader search (last 7 days)
        if not games:
            print(f"No games found for {game_date}, trying broader search")
            start_date = game_date - timedelta(days=7)
            end_date = game_date + timedelta(days=7)
            games = self.db.query(Game).filter(
                Game.game_date >= start_date,
                Game.game_date <= end_date,
                Game.sport == self.sport
            ).order_by(Game.game_date.desc()).limit(20).all()
            print(f"Broader search found {len(games)} games")

        if not games:
            print(f"No games found for {game_date} even with broader search")
            return []

        game_ids = [g.game_id for g in games]
        print(f"Found {len(games)} games for {game_date}: {[g.game_id for g in games]}")
        
        # Get predictions with high confidence and good probabilities
        # Include all bet types: safe, standard, and long_shot
        # Use sport-appropriate bettable stat types (excludes minutes, snaps, etc.)
        from app.config.sport_config import get_bettable_stat_types
        bettable_stat_types = get_bettable_stat_types(self.sport)
        
        # For suggested bets, focus on primary bettable stats
        if self.sport == 'NFL':
            primary_stats = [s for s in bettable_stat_types if s in ['passing_yards', 'rushing_yards', 'receiving_yards', 'receptions']]
        elif self.sport == 'MLB':
            primary_stats = [s for s in bettable_stat_types if s in ['hits', 'home_runs', 'total_bases', 'strikeouts']]
        else:  # NBA
            primary_stats = [s for s in bettable_stat_types if s in ['points', 'rebounds', 'assists', 'three_pointers_made', 'pts+ast+reb']]

        # For NFL, be more lenient with confidence levels and bet types since they tend to be lower
        allowed_confidence = ['HIGH', 'MEDIUM', 'LOW', 'MODEL_ONLY']  # Include MODEL_ONLY
        # Include all bet types for both sports to get more suggestions
        allowed_bet_types = ['safe', 'standard', 'long_shot']

        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id.in_(game_ids),
                Prediction.sport == self.sport,  # CRITICAL: Filter by sport
                Prediction.bet_type.in_(allowed_bet_types),
                Prediction.stat_type.in_(primary_stats),
                Prediction.confidence_level.in_(allowed_confidence)
            )
        ).all()

        print(f"Found {len(predictions)} predictions matching criteria (bet_types: {allowed_bet_types}, confidence: {allowed_confidence})")
        
        # If we don't have enough long shots, lower the confidence requirement for them
        long_shot_count = sum(1 for p in predictions if p.bet_type == 'long_shot')
        if long_shot_count < 5:  # Want at least 5 long shots for variety
            # Use sport-appropriate bettable stat types
            if self.sport == 'NFL':
                long_shot_stats = [s for s in bettable_stat_types if s in ['passing_yards', 'rushing_yards', 'receiving_yards', 'receptions', 'passing_tds', 'rushing_tds', 'receiving_tds']]
            elif self.sport == 'MLB':
                long_shot_stats = [s for s in bettable_stat_types if s in ['hits', 'home_runs', 'total_bases', 'strikeouts']]
            else:  # NBA
                long_shot_stats = [s for s in bettable_stat_types if s in ['points', 'rebounds', 'assists', 'three_pointers_made', 'pts+ast+reb']]
            
            additional_long_shots = self.db.query(Prediction).filter(
                and_(
                    Prediction.game_id.in_(game_ids),
                    Prediction.bet_type == 'long_shot',
                    Prediction.stat_type.in_(long_shot_stats),
                    Prediction.sport == self.sport,  # Ensure sport matches
                    Prediction.confidence_level == 'LOW'  # Include low confidence long shots
                )
            ).limit(10).all()
            predictions.extend(additional_long_shots)
        
        # Filter out injured players
        from app.services.injury_context import InjuryContext
        injury_context = InjuryContext(self.db)
        
        # Score and rank predictions
        scored_predictions = []
        for pred in predictions:
            # Check injury status - skip if Out, Doubtful, or Questionable
            injury_status = injury_context.get_player_injury_status(pred.player_id)
            if injury_status and injury_status['status'] in ['Out', 'Doubtful', 'Questionable']:
                continue  # Skip injured players
            
            # Calculate quality score
            score = self._calculate_bet_score(pred)
            
            # Get probability based on bet type (no fallbacks - use actual data)
            if pred.bet_type == 'safe':
                probability = pred.safe_probability
                line = pred.safe_line
            elif pred.bet_type == 'standard':
                probability = pred.standard_probability
                line = pred.standard_line
            else:  # long_shot
                probability = pred.long_shot_probability
                line = pred.long_shot_line

            # Skip if missing critical data
            if probability is None or line is None:
                continue
            
            # Only include if meets minimum probability (for safe/standard bets)
            # Long shots have lower probability threshold
            if pred.bet_type == 'safe' and probability < min_probability:
                continue
            if pred.bet_type == 'standard' and probability < 0.40:
                continue
            if pred.bet_type == 'long_shot' and (probability < 0.08 or probability > 0.30):
                continue
            if not include_long_shots and pred.bet_type == 'long_shot':
                continue
            
            player = self.db.query(Player).filter(Player.player_id == pred.player_id).first()
            game = self.db.query(Game).filter(Game.game_id == pred.game_id).first()
            
            if not player or not game:
                continue
            
            # Get player's team
            player_team = None
            if player.current_team_id:
                team = self.db.query(Team).filter(Team.team_id == player.current_team_id).first()
                player_team = team.abbreviation if team else None

            # Get last 3 games for this stat type
            historical_data = get_last_n_games_for_stat(
                db=self.db,
                player_id=pred.player_id,
                stat_type=pred.stat_type,
                sport=self.sport,  # Use the correct sport
                n_games=3,
                exclude_game_id=pred.game_id,
                include_lineup_analysis=True,
                current_game_id=pred.game_id
            )
            last_3_games = historical_data['games']
            lineup_context = historical_data['lineup_context']
            
            # Ensure line is positive and reasonable
            final_line = round(float(line) if line is not None and line > 0 else 10.0, 1)
            if final_line <= 0:
                # Use sport-specific defaults instead of generic 10.0
                if self.sport == 'MLB':
                    mlb_fallback_defaults = {
                        'hits': 1.0, 'home_runs': 0.5, 'total_bases': 1.5,
                        'strikeouts': 1.0, 'runs': 0.5, 'rbis': 0.5, 'stolen_bases': 0.2
                    }
                    final_line = mlb_fallback_defaults.get(pred.stat_type, 1.0)
                elif self.sport == 'NFL':
                    final_line = 10.0  # NFL stats are typically higher
                else:  # NBA
                    final_line = 10.0
            
            # MLB SANITY CHECK 1: Reject absurd 10.0 lines for low-value stats
            # CRITICAL: 10.0 is the known NBA-style generic fallback that's inappropriate for MLB
            # For hits/HR/total_bases, even 5.0 would be unusual - 10.0 is always junk data
            # Windows testing: 36× total_bases@10.0 shipped with positive distribution_mean
            # Fix: Skip line≈10.0 unconditionally for MLB low-value stats (ignore distribution_mean)
            if self.sport == 'MLB':
                mlb_low_value_stats = ['hits', 'home_runs', 'total_bases', 'strikeouts', 'runs', 'rbis', 'stolen_bases']
                if pred.stat_type in mlb_low_value_stats and abs(final_line - 10.0) < 0.01:
                    # 10.0 is ALWAYS the generic NBA fallback for these MLB stats - never a real line
                    # Even if distribution_mean exists, line=10.0 means the prediction system used
                    # the generic fallback instead of sport-specific logic
                    print(f"⚠️  Skipping MLB {pred.stat_type} with bogus 10.0 fallback (player {pred.player_id}, line={final_line:.1f})")
                    # Self-check: This catches total_bases@10.0 even when distribution_mean > 0
                    continue
            
            # MLB SANITY CHECK 2: Sport-specific maximum reasonable values
            # These catch prediction bugs before the 5x recent validation
            if self.sport == 'MLB':
                # MLB stats have known reasonable maximums
                mlb_max_values = {
                    'hits': 6.0,  # Even elite hitters rarely get >5 hits in a game
                    'home_runs': 4.0,  # 4 HR in a game is exceptional
                    'rbis': 10.0,  # 10 RBI is extremely rare
                    'total_bases': 18.0,  # 4 HRs = 16 bases, so 18 is a hard ceiling
                    'strikeouts': 20.0,  # For pitchers, 20 K is elite
                    'at_bats': 7.0,  # 7 ABs is a lot even in extra innings
                    'plate_appearances': 8.0
                }
                max_value = mlb_max_values.get(pred.stat_type)
                if max_value and final_line > max_value:
                    print(f"⚠️  WARNING: {player.name} {pred.stat_type} line {final_line} exceeds MLB sanity maximum ({max_value}). Skipping.")
                    continue
            
            # VALIDATION: Only filter extreme outliers that are clearly data errors
            # This should be very lenient - only catch obvious mistakes (e.g., 5x+ recent max)
            # Most predictions are valid even if they differ from recent performance
            if last_3_games and len(last_3_games) > 0:
                recent_values = [g.get('value', 0) for g in last_3_games if g.get('value') is not None]
                if recent_values and len(recent_values) >= 2:  # Need at least 2 games for validation
                    max_recent = max(recent_values)
                    avg_recent = sum(recent_values) / len(recent_values)
                    
                    # Only filter if line is EXTREMELY high compared to recent (5x+ max recent)
                    # This catches obvious data errors like assists showing 50 when player averages 2
                    if max_recent > 0:  # Avoid division by zero
                        if final_line > max_recent * 5.0:
                            print(f"⚠️  WARNING: {player.name} {pred.stat_type} line {final_line} is >5x max recent ({max_recent}). Recent: {recent_values}. Skipping extreme outlier.")
                            continue
            
            # Build reason_strings from confidence_reasons and additional context
            import json
            reason_strings = []
            
            # Parse confidence_reasons JSON if available
            if pred.confidence_reasons:
                try:
                    confidence_reasons = json.loads(pred.confidence_reasons)
                    reason_strings.extend(confidence_reasons)
                except:
                    pass
            
            # Add sample size context
            n_games_effective = pred.n_games_effective or pred.sample_size or 0
            if n_games_effective < 10:
                reason_strings.append(f"Very limited data ({int(n_games_effective)} effective games)")
            elif n_games_effective < 20:
                reason_strings.append(f"Limited data ({int(n_games_effective)} effective games)")
            
            # Add line source note
            if pred.line_source == 'model' or not pred.line_source:
                reason_strings.append("Model-generated line (no sportsbook line available)")
            elif pred.line_source == 'sportsbook':
                reason_strings.append("Based on real sportsbook line")
            
            scored_predictions.append({
                'prediction_id': pred.prediction_id,
                'player_id': pred.player_id,
                'player_name': player.name,
                'player_team': player_team or 'UNK',  # Ensure we always have a team value
                'game_id': pred.game_id,
                'game_date': game.game_date.isoformat() if game else None,
                'stat_type': pred.stat_type,
                'bet_type': pred.bet_type,
                'line': final_line,
                'probability': round(float(probability) if probability is not None else 0.5, 3),
                'confidence_level': pred.confidence_level,
                'confidence_tier': pred.confidence_level,  # Alias for clarity
                'confidence_score': pred.confidence_score,
                'n_games_effective': n_games_effective,
                'line_source': pred.line_source or 'model',
                'volatility_level': pred.volatility_level,
                'score': score,
                'reasoning': pred.reasoning,
                'reason_strings': reason_strings,
                'last_3_games': last_3_games
            })
        
        # Sort by score (highest first)
        scored_predictions.sort(key=lambda x: x['score'], reverse=True)

        print(f"Returning {min(len(scored_predictions), limit)} suggested bets out of {len(scored_predictions)} scored predictions")
        return scored_predictions[:limit]
    
    def _calculate_bet_score(self, prediction: Prediction) -> float:
        """
        Calculate quality score for a bet using calibrated probability and confidence.
        
        Higher score = better bet recommendation.
        Ranks by:
        1. Calibrated probability EDGE over base rate (heavily weighted)
        2. Sample size (n_games_effective)
        3. Confidence tier as multiplier
        4. Line source (real > synthetic)
        """
        score = 0.0
        
        # Get probability and calculate edge over base rate
        if prediction.bet_type == 'safe':
            prob = prediction.safe_probability or 0
            base_rate = 0.67 if self.sport == 'MLB' else 0.52  # Typical safe pick base rate
        elif prediction.bet_type == 'standard':
            prob = prediction.standard_probability or 0
            base_rate = 0.50  # Coin flip
        else:  # long_shot
            prob = prediction.long_shot_probability or 0
            base_rate = 0.20  # Typical long shot base
        
        # Edge = how much better than base rate
        edge = prob - base_rate
        
        # Base score from edge (0-150 points range)
        if edge > 0:
            # Positive edge: scale by magnitude
            score += min(edge * 300, 150)  # Cap at 150
        else:
            # Negative edge: penalize but not eliminate
            score += max(edge * 200, -50)  # Cap penalty at -50
        
        # Add bonus for high absolute probability (safe bets)
        if prediction.bet_type == 'safe' and prob >= 0.70:
            score += 30
        elif prediction.bet_type == 'safe' and prob >= 0.65:
            score += 15
        
        # Sample size bonus (vary based on effective games)
        n_games = prediction.n_games_effective or prediction.sample_size or 0
        if n_games >= 40:
            score += 35
        elif n_games >= 30:
            score += 25
        elif n_games >= 20:
            score += 15
        elif n_games >= 10:
            score += 5
        else:
            # Penalize very small samples more
            score -= 15
        
        # Confidence tier multiplier (apply after base score)
        confidence_tier = prediction.confidence_level or 'LOW'
        if confidence_tier == 'HIGH':
            score *= 1.4
        elif confidence_tier == 'MEDIUM':
            score *= 1.2
        elif confidence_tier == 'LOW':
            score *= 1.0
        elif confidence_tier == 'MODEL_ONLY':
            score *= 0.85  # Less penalty than before
        
        # Line source adjustment (after multiplier)
        if prediction.line_source == 'sportsbook':
            score += 35  # Significant bonus for real lines
        else:
            # Synthetic lines: modest penalty
            score -= 15
        
        # Volatility penalty (reduced)
        if prediction.volatility_level == 'HIGH':
            score -= 15
        elif prediction.volatility_level == 'MEDIUM':
            score -= 5
        
        # Pass reason penalty
        if prediction.pass_reason:
            score -= 30
        
        return max(0, score)
    
    def get_suggested_parlays(
        self,
        game_date: Optional[date] = None,
        limit: int = 5,
        min_legs: int = 2,
        max_legs: int = 4,
        diversify_players: bool = True
    ) -> List[Dict]:
        """
        Get suggested parlay combinations with player diversification.
        
        Args:
            game_date: Date to get suggestions for (default: today)
            limit: Maximum number of parlay suggestions
            min_legs: Minimum number of legs in parlay
            max_legs: Maximum number of legs in parlay
            diversify_players: If True, ensure each player appears in only one parlay
        
        Returns:
            List of suggested parlay dictionaries
        """
        if game_date is None:
            game_date = date.today()
        
        # Get suggested bets first (include long shots for parlay variety)
        # Use lower threshold for NFL since predictions tend to be less confident
        min_prob_threshold = 0.50 if self.sport == 'NFL' else 0.60
        suggested_bets = self.get_suggested_bets(game_date, limit=50, min_probability=min_prob_threshold, include_long_shots=True)
        
        if len(suggested_bets) < min_legs:
            return []
        
        # Generate parlay combinations
        all_parlays = []
        
        # Try different leg counts (2, 3, 4)
        # Ensure we support 2-4 leg parlays as requested
        max_legs = min(max_legs, 4)  # Cap at 4 legs
        for num_legs in range(min_legs, min(max_legs + 1, len(suggested_bets) + 1)):
            # Generate combinations of bets
            for combo in combinations(suggested_bets, num_legs):
                # Filter out combinations with same player within parlay
                player_ids = [bet['player_id'] for bet in combo]
                if len(player_ids) != len(set(player_ids)):
                    continue  # Skip if duplicate players within parlay
                
                # Filter out bets with invalid lines (negative or zero)
                if any(bet.get('line', 0) <= 0 for bet in combo):
                    continue  # Skip parlays with invalid lines
                
                # Calculate combined probability and odds
                combined_prob = 1.0
                for bet in combo:
                    combined_prob *= bet['probability']
                
                # Convert to American odds
                if combined_prob > 0:
                    decimal_odds = 1.0 / combined_prob
                    american_odds = (decimal_odds - 1) * 100
                else:
                    american_odds = None
                
                # Calculate parlay score (higher is better)
                parlay_score = combined_prob * 1000  # Scale up for ranking
                
                # Prefer parlays with mix of stat types
                stat_types = [bet['stat_type'] for bet in combo]
                unique_stats = len(set(stat_types))
                parlay_score += unique_stats * 50  # Bonus for diversity
                
                # Prefer parlays with mix of games (diversify risk)
                game_ids = [bet['game_id'] for bet in combo]
                unique_games = len(set(game_ids))
                parlay_score += unique_games * 30  # Bonus for game diversity
                
                all_parlays.append({
                    'legs': combo,
                    'num_legs': num_legs,
                    'combined_probability': round(combined_prob, 4),
                    'combined_odds': round(american_odds, 0) if american_odds else None,
                    'odds_display': f"+{int(american_odds)}" if american_odds and american_odds > 0 else f"{int(american_odds)}" if american_odds else "N/A",
                    'score': parlay_score,
                    'stat_diversity': unique_stats,
                    'game_diversity': unique_games,
                    'player_ids': set(player_ids)  # Store for diversification check
                })
        
        # Sort by score (highest first)
        all_parlays.sort(key=lambda x: x['score'], reverse=True)
        
        # If diversification is enabled, select parlays ensuring no player overlap
        # But prioritize getting a mix of 2, 3, and 4 leg parlays
        if diversify_players:
            selected_parlays = []
            used_players = set()
            
            # Group parlays by leg count
            parlays_by_legs = {2: [], 3: [], 4: []}
            for parlay in all_parlays:
                num_legs = parlay['num_legs']
                if num_legs in parlays_by_legs:
                    parlays_by_legs[num_legs].append(parlay)
            
            # Try to get at least one of each leg count
            target_counts = {2: limit // 3, 3: limit // 3, 4: limit // 3}
            remaining = limit - sum(target_counts.values())
            target_counts[2] += remaining  # Give remainder to 2-leg parlays
            
            for num_legs in [4, 3, 2]:  # Prioritize higher leg counts
                for parlay in parlays_by_legs[num_legs]:
                    if len(selected_parlays) >= limit:
                        break
                    
                    # Check if this parlay uses any already-used players
                    parlay_players = parlay['player_ids']
                    if parlay_players.isdisjoint(used_players):
                        # No overlap - add this parlay
                        selected_parlays.append(parlay)
                        used_players.update(parlay_players)
                        
                        # Remove player_ids from the dict before returning
                        parlay.pop('player_ids', None)
                        
                        # Check if we've met the target for this leg count
                        current_count = sum(1 for p in selected_parlays if p['num_legs'] == num_legs)
                        if current_count >= target_counts[num_legs]:
                            continue  # Move to next leg count
            
            # If we still have room, fill with any remaining parlays
            for parlay in all_parlays:
                if len(selected_parlays) >= limit:
                    break
                if parlay not in selected_parlays:
                    parlay_players = parlay['player_ids']
                    if parlay_players.isdisjoint(used_players):
                        selected_parlays.append(parlay)
                        used_players.update(parlay_players)
                        parlay.pop('player_ids', None)
            
            return selected_parlays
        else:
            # Return top N without diversification
            for parlay in all_parlays[:limit]:
                parlay.pop('player_ids', None)  # Remove internal tracking field
            return all_parlays[:limit]

    def get_matchup_advantage_parlays(
        self,
        game_date: Optional[date] = None,
        limit: int = 3,
        min_legs: int = 2,
        max_legs: int = 4
    ) -> List[Dict]:
        """
        TEMPORARILY DISABLED: This endpoint was causing timeouts due to complex combination generation.
        Return empty list for now to prevent dashboard timeouts.

        TODO: Re-implement with optimized algorithm or simplify to pre-built parlays.
        """
        # Temporarily return empty list to prevent timeouts
        # This will be re-implemented with a more efficient approach
        return []

        # Add leg details
        games_in_parlay = set()
        for bet in combo:
            games_in_parlay.add(bet['game_id'])

            leg = {
                'prediction_id': bet['prediction_id'],
                'player_id': bet['player_id'],
                'player_name': bet['player_name'],
                'player_team': bet['player_team'],
                'stat_type': bet['stat_type'],
                'line': bet['line'],
                'bet_type': bet['bet_type'],
                'probability': bet['probability'],
                'confidence_level': bet.get('confidence_level', 'medium'),
                'volatility_level': bet.get('volatility_level', 'medium'),
                'reasoning': bet.get('reasoning', ''),
                'last_3_games': bet.get('last_3_games', []),
                'game_id': bet.get('game_id'),
                'opponent_team_abbreviation': bet.get('opponent_team_abbreviation', '')
            }
            parlay['legs'].append(leg)

        # Calculate diversification score (higher is better)
        parlay['game_diversity'] = len(games_in_parlay)

        # Prefer parlays with more diverse games
        diversification_score = len(games_in_parlay) * 10

        # Prefer higher combined probability
        diversification_score += combined_prob * 5

        parlay['diversification_score'] = diversification_score

        all_parlays.append(parlay)

        # Sort by diversification score (higher is better)
        all_parlays.sort(key=lambda x: x['diversification_score'], reverse=True)

        return all_parlays[:limit]

    def get_matchup_advantage_bets(
        self,
        game_date: Optional[date] = None,
        limit: int = 10,
        only_hot: bool = True
    ) -> List[Dict]:
        """
        TEMPORARILY DISABLED: This endpoint was causing timeouts due to calling get_suggested_bets with large limits.
        Return empty list for now to prevent dashboard timeouts.

        TODO: Re-implement with direct database queries instead of calling get_suggested_bets.
        """
        # Temporarily return empty list to prevent timeouts
        # This will be re-implemented with a more direct approach
        return []

    def get_suggested_parlays_by_stat_mix(
        self,
        game_date: Optional[date] = None,
        limit: int = 5,
        diversify_players: bool = True
    ) -> List[Dict]:
        """
        Get suggested parlays with a mix of stat types (points, rebounds, assists).
        
        This ensures parlays have variety rather than all the same stat type.
        Also ensures player diversification across all suggested parlays.
        """
        if game_date is None:
            game_date = date.today()
        
        # Get suggested bets grouped by stat type
        # Use lower threshold for NFL/MLB since predictions tend to be less confident
        min_prob_threshold = 0.50 if self.sport in ('NFL', 'MLB') else 0.60
        suggested_bets = self.get_suggested_bets(game_date, limit=30, min_probability=min_prob_threshold)
        
        # Use sport-appropriate stat types
        if self.sport == 'NFL':
            stat_categories = {
                'passing': [b for b in suggested_bets if 'passing' in b['stat_type']],
                'rushing': [b for b in suggested_bets if 'rushing' in b['stat_type']],
                'receiving': [b for b in suggested_bets if 'receiving' in b['stat_type']]
            }
            required_stats = ['passing', 'rushing', 'receiving']
        elif self.sport == 'MLB':
            stat_categories = {
                'hits': [b for b in suggested_bets if b['stat_type'] == 'hits'],
                'home_runs': [b for b in suggested_bets if b['stat_type'] == 'home_runs'],
                'strikeouts': [b for b in suggested_bets if b['stat_type'] == 'strikeouts']
            }
            required_stats = ['hits', 'home_runs', 'strikeouts']
        else:  # NBA
            stat_categories = {
                'points': [b for b in suggested_bets if b['stat_type'] == 'points'],
                'rebounds': [b for b in suggested_bets if b['stat_type'] == 'rebounds'],
                'assists': [b for b in suggested_bets if b['stat_type'] == 'assists']
            }
            required_stats = ['points', 'rebounds', 'assists']

        all_parlays = []

        # Create 3-leg parlays with one of each stat type
        if all(len(stat_categories[stat]) > 0 for stat in required_stats):

            # Take top bet from each stat type
            for stat1_bet in stat_categories[required_stats[0]][:3]:
                for stat2_bet in stat_categories[required_stats[1]][:3]:
                    for stat3_bet in stat_categories[required_stats[2]][:3]:
                        # Ensure different players within parlay
                        if (stat1_bet['player_id'] != stat2_bet['player_id'] and
                            stat1_bet['player_id'] != stat3_bet['player_id'] and
                            stat2_bet['player_id'] != stat3_bet['player_id']):

                            combo = [stat1_bet, stat2_bet, stat3_bet]
                            combined_prob = stat1_bet['probability'] * stat2_bet['probability'] * stat3_bet['probability']
                            
                            if combined_prob > 0:
                                decimal_odds = 1.0 / combined_prob
                                american_odds = (decimal_odds - 1) * 100
                            else:
                                american_odds = None
                            
                            all_parlays.append({
                                'legs': combo,
                                'num_legs': 3,
                                'combined_probability': round(combined_prob, 4),
                                'combined_odds': round(american_odds, 0) if american_odds else None,
                                'odds_display': f"+{int(american_odds)}" if american_odds and american_odds > 0 else f"{int(american_odds)}" if american_odds else "N/A",
                                'stat_diversity': 3,  # All three stat types
                                'player_ids': {stat1_bet['player_id'], stat2_bet['player_id'], stat3_bet['player_id']}
                            })
        
        # Create 4-leg parlays: one of each stat type + one extra (different player)
        if all(len(stat_categories[stat]) > 0 for stat in required_stats):

            for stat1_bet in stat_categories[required_stats[0]][:3]:
                for stat2_bet in stat_categories[required_stats[1]][:3]:
                    for stat3_bet in stat_categories[required_stats[2]][:3]:
                        # Add a 4th leg from any stat type (must be different player)
                        for fourth_stat in required_stats:
                            for fourth_bet in stat_categories[fourth_stat][:5]:
                                player_ids = {stat1_bet['player_id'], stat2_bet['player_id'],
                                            stat3_bet['player_id'], fourth_bet['player_id']}
                                if len(player_ids) == 4:  # All different players
                                    combo = [stat1_bet, stat2_bet, stat3_bet, fourth_bet]
                                    combined_prob = (stat1_bet['probability'] * stat2_bet['probability'] *
                                                   stat3_bet['probability'] * fourth_bet['probability'])

                                    if combined_prob > 0:
                                        decimal_odds = 1.0 / combined_prob
                                        american_odds = (decimal_odds - 1) * 100
                                    else:
                                        american_odds = None

                                    all_parlays.append({
                                        'legs': combo,
                                        'num_legs': 4,
                                        'combined_probability': round(combined_prob, 4),
                                        'combined_odds': round(american_odds, 0) if american_odds else None,
                                        'odds_display': f"+{int(american_odds)}" if american_odds and american_odds > 0 else f"{int(american_odds)}" if american_odds else "N/A",
                                        'stat_diversity': len(set([b['stat_type'] for b in combo])),
                                        'player_ids': player_ids
                                    })
                                    break  # Only one 4-leg per combo
                            break  # Only try one stat type for 4th leg
        
        # Also create 2-leg parlays with different stat types
        if self.sport == 'NFL':
            stat_pairs = [('passing', 'rushing'), ('passing', 'receiving'), ('rushing', 'receiving')]
        elif self.sport == 'MLB':
            stat_pairs = [('hits', 'home_runs'), ('hits', 'strikeouts'), ('home_runs', 'strikeouts')]
        else:
            stat_pairs = [('points', 'rebounds'), ('points', 'assists'), ('rebounds', 'assists')]

        for stat1, stat2 in stat_pairs:
            if len(stat_categories[stat1]) > 0 and len(stat_categories[stat2]) > 0:
                for bet1 in stat_categories[stat1][:5]:
                    for bet2 in stat_categories[stat2][:5]:
                        if bet1['player_id'] != bet2['player_id']:
                            combo = [bet1, bet2]
                            combined_prob = bet1['probability'] * bet2['probability']

                            if combined_prob > 0:
                                decimal_odds = 1.0 / combined_prob
                                american_odds = (decimal_odds - 1) * 100
                            else:
                                american_odds = None

                            all_parlays.append({
                                'legs': combo,
                                'num_legs': 2,
                                'combined_probability': round(combined_prob, 4),
                                'combined_odds': round(american_odds, 0) if american_odds else None,
                                'odds_display': f"+{int(american_odds)}" if american_odds and american_odds > 0 else f"{int(american_odds)}" if american_odds else "N/A",
                                'stat_diversity': 2,
                                'player_ids': {bet1['player_id'], bet2['player_id']}
                            })
        
        # Sort by combined probability (highest first)
        all_parlays.sort(key=lambda x: x['combined_probability'], reverse=True)
        
        # If diversification is enabled, select parlays ensuring no player overlap
        # But prioritize getting a mix of 2, 3, and 4 leg parlays
        if diversify_players:
            selected_parlays = []
            used_players = set()
            
            # Group parlays by leg count
            parlays_by_legs = {2: [], 3: [], 4: []}
            for parlay in all_parlays:
                num_legs = parlay['num_legs']
                if num_legs in parlays_by_legs:
                    parlays_by_legs[num_legs].append(parlay)
            
            # Try to get at least one of each leg count
            target_counts = {2: limit // 3, 3: limit // 3, 4: limit // 3}
            remaining = limit - sum(target_counts.values())
            target_counts[2] += remaining  # Give remainder to 2-leg parlays
            
            for num_legs in [4, 3, 2]:  # Prioritize higher leg counts
                for parlay in parlays_by_legs[num_legs]:
                    if len(selected_parlays) >= limit:
                        break
                    
                    parlay_players = parlay['player_ids']
                    if parlay_players.isdisjoint(used_players):
                        selected_parlays.append(parlay)
                        used_players.update(parlay_players)
                        parlay.pop('player_ids', None)
                        
                        # Check if we've met the target for this leg count
                        current_count = sum(1 for p in selected_parlays if p['num_legs'] == num_legs)
                        if current_count >= target_counts[num_legs]:
                            continue  # Move to next leg count
            
            # If we still have room, fill with any remaining parlays
            for parlay in all_parlays:
                if len(selected_parlays) >= limit:
                    break
                if parlay not in selected_parlays:
                    parlay_players = parlay['player_ids']
                    if parlay_players.isdisjoint(used_players):
                        selected_parlays.append(parlay)
                        used_players.update(parlay_players)
                        parlay.pop('player_ids', None)
            
            return selected_parlays
        else:
            # Return top N without diversification
            for parlay in all_parlays[:limit]:
                parlay.pop('player_ids', None)
            return all_parlays[:limit]
    
    def get_safe_long_parlays(
        self,
        game_date: Optional[date] = None,
        limit: int = 3,
        num_legs: int = 12,
        min_leg_probability: float = 0.75,  # Each leg should be at least 75% likely (default, can be adjusted)
        exclude_player_ids: Optional[List[int]] = None  # Player IDs to exclude from generation
    ) -> List[Dict]:
        """
        Get long parlays (10-15 legs) made of very safe bets.
        
        The idea: Combine many high-probability bets to create a long shot parlay
        with good odds, where each individual leg is very likely to hit.
        
        Args:
            game_date: Date to get suggestions for (default: today)
            limit: Maximum number of parlay suggestions
            num_legs: Number of legs in the parlay (10-15)
            min_leg_probability: Minimum probability for each leg (default: 0.80 = 80%)
        
        Returns:
            List of safe long parlay dictionaries
        """
        if game_date is None:
            game_date = date.today()
        
        # Get games for the date (include finished games for historical viewing)
        games = self.db.query(Game).filter(
            and_(
                Game.game_date == game_date,
                Game.sport == self.sport  # Filter by sport
            )
        ).all()
        
        if not games:
            return []
        
        game_ids = [g.game_id for g in games]
        
        # Get sport-appropriate bettable stat types (excludes minutes, snaps, etc.)
        from app.config.sport_config import get_bettable_stat_types
        bettable_stat_types = get_bettable_stat_types(self.sport)
        
        # For safe long parlays, use bettable stats only
        if self.sport == 'NFL':
            safe_stat_types = [s for s in bettable_stat_types if s in ['passing_yards', 'rushing_yards', 'receiving_yards', 'receptions']]
        elif self.sport == 'MLB':
            safe_stat_types = [s for s in bettable_stat_types if s in ['hits', 'home_runs', 'total_bases', 'strikeouts']]
        else:  # NBA
            # Include points, rebounds, assists, three_pointers_made, and pts+ast+reb
            safe_stat_types = [s for s in bettable_stat_types if s in ['points', 'rebounds', 'assists', 'three_pointers_made', 'pts+ast+reb']]
        
        # Get predictions with very high safe probabilities (≥75% default)
        # Use safe_line but require higher probability threshold
        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id.in_(game_ids),
                Prediction.sport == self.sport,  # CRITICAL: Filter by sport
                Prediction.bet_type == 'safe',  # Only safe bets
                Prediction.stat_type.in_(safe_stat_types),
                Prediction.safe_probability >= min_leg_probability,  # Very safe threshold
                Prediction.confidence_level.in_(['HIGH', 'MEDIUM', 'LOW', 'MODEL_ONLY'])  # Include MODEL_ONLY
            )
        ).order_by(Prediction.safe_probability.desc()).all()
        
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
        
        if len(predictions) < num_legs:
            return []  # Not enough safe bets available
        
        # Convert to bet format (optimized with batch queries)
        player_ids = list(set([p.player_id for p in predictions]))
        game_ids = list(set([p.game_id for p in predictions]))
        
        # Batch load all players, games, and teams
        players_dict = {p.player_id: p for p in self.db.query(Player).filter(Player.player_id.in_(player_ids)).all()}
        games_dict = {g.game_id: g for g in self.db.query(Game).filter(Game.game_id.in_(game_ids)).all()}
        team_ids = list(set([p.current_team_id for p in players_dict.values() if p.current_team_id]))
        teams_dict = {t.team_id: t for t in self.db.query(Team).filter(Team.team_id.in_(team_ids)).all()} if team_ids else {}
        
        safe_bets = []
        for pred in predictions:
            player = players_dict.get(pred.player_id)
            game = games_dict.get(pred.game_id)
            
            if not player or not game:
                continue
            
            # Get player's team
            player_team = None
            if player.current_team_id:
                team = teams_dict.get(player.current_team_id)
                player_team = team.abbreviation if team else None

            # Get last 3 games for this stat type
            historical_data = get_last_n_games_for_stat(
                db=self.db,
                player_id=pred.player_id,
                stat_type=pred.stat_type,
                sport=self.sport,  # Use the correct sport
                n_games=3,
                exclude_game_id=pred.game_id,
                include_lineup_analysis=True,
                current_game_id=pred.game_id
            )
            last_3_games = historical_data['games']
            lineup_context = historical_data['lineup_context']
            
            # Ensure line is valid (positive and not None)
            safe_line = pred.safe_line
            probability = pred.safe_probability
            if safe_line is None or safe_line <= 0 or probability is None:
                continue  # Skip bets with invalid lines or probabilities
            
            # SANITY CHECK: Sport-specific maximum reasonable values
            if self.sport == 'MLB':
                mlb_max_values = {
                    'hits': 6.0, 'home_runs': 4.0, 'rbis': 10.0, 
                    'total_bases': 18.0, 'strikeouts': 20.0,
                    'at_bats': 7.0, 'plate_appearances': 8.0
                }
                max_value = mlb_max_values.get(pred.stat_type)
                if max_value and safe_line > max_value:
                    print(f"⚠️  WARNING: {player.name} {pred.stat_type} safe_line {safe_line} exceeds MLB sanity maximum ({max_value}). Skipping.")
                    continue
            
            # VALIDATION: Only filter extreme outliers that are clearly data errors
            # This should be very lenient - only catch obvious mistakes (e.g., 5x+ recent max)
            if last_3_games and len(last_3_games) > 0:
                recent_values = [g.get('value', 0) for g in last_3_games if g.get('value') is not None]
                if recent_values and len(recent_values) >= 2:  # Need at least 2 games for validation
                    max_recent = max(recent_values)
                    
                    # Only filter if line is EXTREMELY high compared to recent (5x+ max recent)
                    if max_recent > 0 and safe_line > max_recent * 5.0:
                        print(f"⚠️  WARNING: {player.name} {pred.stat_type} line {safe_line} is >5x max recent ({max_recent}). Recent: {recent_values}. Skipping extreme outlier.")
                        continue
            
            safe_bets.append({
                'prediction_id': pred.prediction_id,
                'player_id': pred.player_id,
                'player_name': player.name,
                'player_team': player_team or 'UNK',  # Ensure we always have a team value
                'game_id': pred.game_id,
                'stat_type': pred.stat_type,
                'bet_type': 'safe',
                'line': safe_line,
                'probability': probability,
                'confidence_level': pred.confidence_level or 'MEDIUM',
                'volatility_level': pred.volatility_level or 'MEDIUM',
                'last_3_games': last_3_games
            })
        
        # Use a smarter greedy algorithm instead of generating all combinations
        # Generating C(38, 12) = billions of combinations is too slow!
        # Instead, we'll use a greedy approach to build good parlays
        
        selected_parlays = []
        used_players = set()
        
        # Group bets by game for better diversification
        bets_by_game = {}
        for bet in safe_bets:
            game_id = bet['game_id']
            if game_id not in bets_by_game:
                bets_by_game[game_id] = []
            bets_by_game[game_id].append(bet)
        
        # Try to build limit number of parlays
        for parlay_idx in range(limit):
            if len(used_players) >= len(safe_bets):
                break  # No more unique players available
            
            # Build one parlay using greedy selection
            parlay_legs = []
            parlay_players = set()
            parlay_games = set()
            
            # Start with highest probability bets, ensuring diversity
            # Exclude players that were in previous parlays AND any explicitly excluded players
            exclude_set = used_players.copy()
            if exclude_player_ids:
                exclude_set.update(exclude_player_ids)
            available_bets = [b for b in safe_bets if b['player_id'] not in exclude_set]
            
            # Sort by probability (highest first) but also consider game diversity
            available_bets.sort(key=lambda x: (
                x['probability'],  # Higher probability is better
                -len([b for b in available_bets if b['game_id'] == x['game_id']])  # Prefer games with fewer available bets
            ), reverse=True)
            
            # Select num_legs bets, ensuring all different players
            for bet in available_bets:
                if len(parlay_legs) >= num_legs:
                    break
                
                # Skip if we already have this player
                if bet['player_id'] in parlay_players:
                    continue
                
                parlay_legs.append(bet)
                parlay_players.add(bet['player_id'])
                parlay_games.add(bet['game_id'])
            
            # If we don't have enough legs, skip this parlay
            if len(parlay_legs) < num_legs:
                break
            
            # Calculate combined probability
            combined_prob = 1.0
            for bet in parlay_legs:
                combined_prob *= bet['probability']
            
            # Convert to odds
            if combined_prob > 0:
                decimal_odds = 1.0 / combined_prob
                american_odds = (decimal_odds - 1) * 100
            else:
                american_odds = None
            
            parlay = {
                'legs': parlay_legs,
                'num_legs': num_legs,
                'combined_probability': round(combined_prob, 4),
                'combined_odds': round(american_odds, 0) if american_odds else None,
                'odds_display': f"+{int(american_odds)}" if american_odds and american_odds > 0 else f"{int(american_odds)}" if american_odds else "N/A",
                'min_leg_probability': min(bet['probability'] for bet in parlay_legs),
                'avg_leg_probability': sum(bet['probability'] for bet in parlay_legs) / len(parlay_legs),
                'game_diversity': len(parlay_games),
                'player_ids': parlay_players
            }
            
            selected_parlays.append(parlay)
            used_players.update(parlay_players)
        
        # Remove player_ids from response (internal tracking only)
        for parlay in selected_parlays:
            parlay.pop('player_ids', None)
        
        return selected_parlays
    
    def get_same_game_parlays(
        self,
        game_id: int,
        limit: int = 5,
        num_legs: int = 3,
        min_leg_probability: float = 0.70
    ) -> List[Dict]:
        """
        Get parlay suggestions for a specific game (all legs from same game).
        
        Args:
            game_id: Game ID
            limit: Maximum number of parlay suggestions
            num_legs: Number of legs in parlay (2-4)
            min_leg_probability: Minimum probability for each leg
        
        Returns:
            List of same-game parlay dictionaries
        """
        # Verify game exists
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return []
        
        # Get predictions for this game with good probabilities
        # Get all predictions (safe, standard, long_shot) and pick the best one per player-stat combo
        # Only include bettable stat types (excludes minutes)
        from app.config.sport_config import get_bettable_stat_types
        bettable_stat_types = get_bettable_stat_types(self.sport)
        
        # For NBA same-game parlays, use bettable stats: points, rebounds, assists, three_pointers_made, pts+ast+reb
        if self.sport == 'NBA':
            sgp_stat_types = [s for s in bettable_stat_types if s in ['points', 'rebounds', 'assists', 'three_pointers_made', 'pts+ast+reb']]
        elif self.sport == 'MLB':
            sgp_stat_types = [s for s in bettable_stat_types if s in ['hits', 'home_runs', 'total_bases', 'strikeouts']]
        else:  # NFL
            sgp_stat_types = bettable_stat_types
        
        all_predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id == game_id,
                Prediction.stat_type.in_(sgp_stat_types),
                Prediction.bet_type.in_(['safe', 'standard']),  # Only safe/standard for same-game parlays
                Prediction.confidence_level.in_(['HIGH', 'MEDIUM', 'LOW', 'MODEL_ONLY'])  # Include MODEL_ONLY
            )
        ).all()
        
        # Filter out injured/out players
        from app.services.injury_context import InjuryContext
        injury_context = InjuryContext(self.db)
        
        # Group by player_id + stat_type, keep the one with highest probability
        best_predictions = {}
        for pred in all_predictions:
            # Check injury status
            injury_status = injury_context.get_player_injury_status(pred.player_id)
            if injury_status and injury_status['status'] in ['Out', 'Doubtful']:
                continue  # Skip injured players
            
            # Determine which probability to use
            if pred.bet_type == 'safe' and pred.safe_probability:
                prob = pred.safe_probability
            elif pred.bet_type == 'standard' and pred.standard_probability:
                prob = pred.standard_probability
            else:
                continue  # No valid probability
            
            if prob < min_leg_probability:
                continue  # Doesn't meet threshold
            
            # Keep the best prediction per player-stat combo
            key = (pred.player_id, pred.stat_type)
            if key not in best_predictions or prob > best_predictions[key][1]:
                best_predictions[key] = (pred, prob)
        
        available_predictions = [pred for pred, _ in best_predictions.values()]
        
        if len(available_predictions) < num_legs:
            return []
        
        # Convert to bet format
        player_ids = list(set([p.player_id for p in available_predictions]))
        players_dict = {p.player_id: p for p in self.db.query(Player).filter(Player.player_id.in_(player_ids)).all()}
        team_ids = list(set([p.current_team_id for p in players_dict.values() if p.current_team_id]))
        teams_dict = {t.team_id: t for t in self.db.query(Team).filter(Team.team_id.in_(team_ids)).all()} if team_ids else {}
        
        bets = []
        for pred in available_predictions:
            player = players_dict.get(pred.player_id)
            if not player:
                continue
            
            # Use safe or standard line/probability based on bet_type
            # We already filtered by probability above, so just use the appropriate one
            if pred.bet_type == 'safe' and pred.safe_probability:
                line = pred.safe_line
                probability = pred.safe_probability
                bet_type = 'safe'
            elif pred.bet_type == 'standard' and pred.standard_probability:
                line = pred.standard_line
                probability = pred.standard_probability
                bet_type = 'standard'
            else:
                continue  # Shouldn't happen, but safety check
            
            # SANITY CHECK: Sport-specific maximum reasonable values
            if self.sport == 'MLB' and line:
                mlb_max_values = {
                    'hits': 6.0, 'home_runs': 4.0, 'rbis': 10.0,
                    'total_bases': 18.0, 'strikeouts': 20.0,
                    'at_bats': 7.0, 'plate_appearances': 8.0
                }
                max_value = mlb_max_values.get(pred.stat_type)
                if max_value and line > max_value:
                    print(f"⚠️  WARNING: SGP {player.name} {pred.stat_type} line {line} exceeds MLB sanity maximum ({max_value}). Skipping.")
                    continue
            
            team = teams_dict.get(player.current_team_id) if player.current_team_id else None

            # Get last 3 games for this stat type
            historical_data = get_last_n_games_for_stat(
                db=self.db,
                player_id=pred.player_id,
                stat_type=pred.stat_type,
                sport=self.sport,  # Use the correct sport
                n_games=3,
                exclude_game_id=pred.game_id,
                include_lineup_analysis=True,
                current_game_id=pred.game_id
            )
            last_3_games = historical_data['games']
            lineup_context = historical_data['lineup_context']
            
            # VALIDATION: Only filter extreme outliers that are clearly data errors
            # This should be very lenient - only catch obvious mistakes (e.g., 5x+ recent max)
            if last_3_games and len(last_3_games) > 0:
                recent_values = [g.get('value', 0) for g in last_3_games if g.get('value') is not None]
                if recent_values and len(recent_values) >= 2:  # Need at least 2 games for validation
                    max_recent = max(recent_values)
                    
                    # Only filter if line is EXTREMELY high compared to recent (5x+ max recent)
                    if max_recent > 0 and line > max_recent * 5.0:
                        print(f"⚠️  WARNING: {player.name} {pred.stat_type} line {line} is >5x max recent ({max_recent}). Recent: {recent_values}. Skipping extreme outlier.")
                        continue
            
            # DEBUG: Log if we see suspicious assists values
            if pred.stat_type == 'assists' and last_3_games:
                for game_data in last_3_games:
                    if game_data.get('value', 0) > 10:
                        print(f"⚠️  DEBUG: {player.name} assists showing value {game_data.get('value')} for game {game_data.get('game_date')} vs {game_data.get('opponent')}")
                        print(f"    stat_type: {pred.stat_type}, stat_column should be: assists")
                        # Verify what the actual stat value is
                        from app.models import PlayerGameStat, Game as GameModel
                        game_obj = self.db.query(GameModel).filter(GameModel.game_date == game_data.get('game_date')).first()
                        if game_obj:
                            stat = self.db.query(PlayerGameStat).filter(
                                PlayerGameStat.player_id == pred.player_id,
                                PlayerGameStat.game_id == game_obj.game_id
                            ).first()
                            if stat:
                                print(f"    Actual DB values: {stat.points} PTS, {stat.rebounds} REB, {stat.assists} AST")
            
            bets.append({
                'prediction_id': pred.prediction_id,
                'player_id': pred.player_id,
                'player_name': player.name,
                'player_team': team.abbreviation if team else None,
                'game_id': pred.game_id,
                'stat_type': pred.stat_type,
                'bet_type': bet_type,
                'line': line,
                'probability': probability,
                'confidence_level': pred.confidence_level,
                'last_3_games': last_3_games
            })
        
        if len(bets) < num_legs:
            return []
        
        # Generate same-game parlays using greedy algorithm
        selected_parlays = []
        used_players = set()
        
        # Group bets by stat type for diversity (only bettable stats)
        bets_by_stat = {}
        for stat_type in ['points', 'rebounds', 'assists', 'three_pointers_made', 'pts+ast+reb']:
            bets_by_stat[stat_type] = [b for b in bets if b['stat_type'] == stat_type]
        
        # Try to build parlays with stat diversity
        for parlay_idx in range(limit):
            if len(used_players) >= len(bets):
                break
            
            parlay_legs = []
            parlay_players = set()
            parlay_stats = set()
            
            # Prefer different stat types
            available_bets = [b for b in bets if b['player_id'] not in used_players]
            
            # Sort to prioritize different stat types and higher probabilities
            available_bets.sort(key=lambda x: (
                len([b for b in parlay_legs if b['stat_type'] == x['stat_type']]),  # Prefer different stats
                -x['probability']  # Then by probability
            ))
            
            for bet in available_bets:
                if len(parlay_legs) >= num_legs:
                    break
                
                # Skip if we already have this player
                if bet['player_id'] in parlay_players:
                    continue
                
                parlay_legs.append(bet)
                parlay_players.add(bet['player_id'])
                parlay_stats.add(bet['stat_type'])
            
            if len(parlay_legs) < num_legs:
                break
            
            # Calculate combined probability
            combined_prob = 1.0
            for bet in parlay_legs:
                combined_prob *= bet['probability']
            
            # Convert to odds
            if combined_prob > 0:
                decimal_odds = 1.0 / combined_prob
                american_odds = (decimal_odds - 1) * 100
            else:
                american_odds = None
            
            parlay = {
                'legs': parlay_legs,
                'num_legs': num_legs,
                'combined_probability': round(combined_prob, 4),
                'combined_odds': round(american_odds, 0) if american_odds else None,
                'odds_display': f"+{int(american_odds)}" if american_odds and american_odds > 0 else f"{int(american_odds)}" if american_odds else "N/A",
                'min_leg_probability': min(bet['probability'] for bet in parlay_legs),
                'avg_leg_probability': sum(bet['probability'] for bet in parlay_legs) / len(parlay_legs),
                'stat_diversity': len(parlay_stats),
                'game_id': game_id
            }
            
            selected_parlays.append(parlay)
            used_players.update(parlay_players)
        
        return selected_parlays

