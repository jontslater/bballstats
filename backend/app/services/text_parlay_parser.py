"""
Text Parlay Parser

Parses natural language text into parlay bets.
Example: "LeBron Over 25 points, AD Over 10 rebounds, Curry Over 30 points"
"""
import re
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.player import Player
from app.models.prediction import Prediction
from app.models.game import Game
from datetime import date, datetime


class TextParlayParser:
    """Parse text input into parlay bets."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def parse_text(self, text: str, game_date: Optional[date] = None) -> List[Dict]:
        """
        Parse text into bet components.
        
        Examples:
        - "LeBron Over 25 points"
        - "AD Over 10 rebounds"
        - "Curry Over 30 points, Tatum Over 20 points"
        - "LeBron James Over 25.5 PTS"
        - "Anthony Davis Under 12 REB"
        
        Returns:
            List of parsed bet dictionaries with:
            - player_name: str
            - stat_type: str (points, rebounds, assists)
            - bet_type: str (Over, Under)
            - line: float
            - confidence: float (0-1, how confident we are in the match)
        """
        # Normalize text
        text = text.strip()
        
        # Split by common delimiters (comma, semicolon, newline, "and")
        # Try to split intelligently
        parts = re.split(r'[,;\n]|(?:\s+and\s+)', text, flags=re.IGNORECASE)
        parts = [p.strip() for p in parts if p.strip()]
        
        parsed_bets = []
        
        for part in parts:
            bet = self._parse_single_bet(part)
            if bet:
                parsed_bets.append(bet)
        
        return parsed_bets
    
    def _parse_single_bet(self, text: str) -> Optional[Dict]:
        """Parse a single bet from text."""
        # Patterns to match:
        # "Player Name Over/Under X.X points/rebounds/assists"
        # "Player Name Over/Under X.X PTS/REB/AST"
        # "Player Name O/U X.X points/rebounds/assists"
        
        # Normalize stat type abbreviations
        text = re.sub(r'\bPTS\b', 'points', text, flags=re.IGNORECASE)
        text = re.sub(r'\bREB\b', 'rebounds', text, flags=re.IGNORECASE)
        text = re.sub(r'\bAST\b', 'assists', text, flags=re.IGNORECASE)
        
        # Match pattern: [Player Name] [Over/Under/O/U] [Number] [stat type]
        pattern = r'(.+?)\s+(Over|Under|O|U)\s+([\d.]+)\s+(points|rebounds|assists|point|rebound|assist)'
        match = re.search(pattern, text, re.IGNORECASE)
        
        if not match:
            return None
        
        player_name = match.group(1).strip()
        bet_direction = match.group(2).strip()
        line_value = float(match.group(3))
        stat_type = match.group(4).strip().lower()
        
        # Normalize stat type
        if stat_type.startswith('point'):
            stat_type = 'points'
        elif stat_type.startswith('rebound'):
            stat_type = 'rebounds'
        elif stat_type.startswith('assist'):
            stat_type = 'assists'
        
        # Normalize bet direction
        if bet_direction.upper() in ['OVER', 'O']:
            bet_type = 'Over'
        elif bet_direction.upper() in ['UNDER', 'U']:
            bet_type = 'Under'
        else:
            return None
        
        return {
            'player_name': player_name,
            'stat_type': stat_type,
            'bet_type': bet_type,
            'line': line_value,
            'confidence': 1.0  # Will be adjusted when matching
        }
    
    def match_to_predictions(
        self, 
        parsed_bets: List[Dict], 
        game_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Match parsed bets to actual predictions.
        
        Returns:
            List of matched bets with prediction_id, game_id, player_id, etc.
        """
        matched_bets = []
        
        for bet in parsed_bets:
            match_result = self._match_bet_to_prediction(bet, game_date)
            if match_result:
                matched_bets.append(match_result)
        
        return matched_bets
    
    def _match_bet_to_prediction(
        self, 
        bet: Dict, 
        game_date: Optional[date] = None
    ) -> Optional[Dict]:
        """Match a single bet to a prediction."""
        player_name = bet['player_name']
        stat_type = bet['stat_type']
        bet_type = bet['bet_type']
        line = bet['line']
        
        # Search for player by name (smart matching)
        # Strategy: Try last name first (most common), then full name, then first name
        
        # Normalize input: remove common prefixes/suffixes and split
        name_parts = player_name.strip().split()
        if not name_parts:
            return None
        
        # Get last name (usually the last word)
        last_name = name_parts[-1]
        first_name = name_parts[0] if len(name_parts) > 1 else None
        
        # Try 1: Exact match (full name)
        player = self.db.query(Player).filter(
            Player.name.ilike(player_name)
        ).first()
        
        if not player:
            # Try 2: Last name match (most common use case)
            # Check if multiple players have this last name
            last_name_matches = self.db.query(Player).filter(
                Player.name.ilike(f'%{last_name}%')
            ).all()
            
            if len(last_name_matches) == 1:
                # Only one player with this last name - use it
                player = last_name_matches[0]
            elif len(last_name_matches) > 1:
                # Multiple players with same last name - try to narrow down
                # If user provided first name, use it
                if first_name:
                    player = self.db.query(Player).filter(
                        and_(
                            Player.name.ilike(f'%{last_name}%'),
                            Player.name.ilike(f'{first_name}%')
                        )
                    ).first()
                
                # If still no match, try partial first name match
                if not player and first_name and len(first_name) > 2:
                    player = self.db.query(Player).filter(
                        and_(
                            Player.name.ilike(f'%{last_name}%'),
                            Player.name.ilike(f'%{first_name[:3]}%')
                        )
                    ).first()
        
        if not player:
            # Try 3: Contains match (fallback)
            player = self.db.query(Player).filter(
                Player.name.ilike(f'%{player_name}%')
            ).first()
        
        if not player:
            return None
        
        # Find predictions for this player
        query = self.db.query(Prediction).filter(
            and_(
                Prediction.player_id == player.player_id,
                Prediction.stat_type == stat_type,
                Prediction.bet_type.in_(['safe', 'standard', 'long_shot'])
            )
        )
        
        # Filter by game date if provided
        if game_date:
            query = query.join(Game).filter(Game.game_date == game_date)
        
        predictions = query.order_by(Prediction.created_at.desc()).limit(5).all()
        
        # If no predictions exist, we'll still create a play using player's historical stats
        if not predictions:
            # Get player's recent game stats to estimate probability
            from app.models.player_game_stat import PlayerGameStat
            from datetime import datetime, timedelta
            
            # Get last 10 games for this player
            # We'll filter by stat value being > 0 to ensure they played
            recent_stats = self.db.query(PlayerGameStat).join(
                Game, PlayerGameStat.game_id == Game.game_id
            ).filter(
                and_(
                    PlayerGameStat.player_id == player.player_id,
                    Game.game_status == 'finished',
                    PlayerGameStat.minutes_played > 0  # Ensure they actually played
                )
            ).order_by(Game.game_date.desc()).limit(10).all()
            
            if recent_stats:
                # Calculate average and use it to estimate probability
                # Get the stat value based on stat_type
                values = []
                for stat in recent_stats:
                    if stat_type == 'points':
                        values.append(stat.points or 0)
                    elif stat_type == 'rebounds':
                        values.append(stat.rebounds or 0)
                    elif stat_type == 'assists':
                        values.append(stat.assists or 0)
                    elif stat_type == 'minutes':
                        values.append(stat.minutes_played or 0)
                
                avg_value = sum(values) / len(values) if values else 0
                std_dev = ((sum((x - avg_value) ** 2 for x in values) / len(values)) ** 0.5) if len(values) > 1 else avg_value * 0.2
                
                # Estimate probability based on line vs average
                if bet_type == 'Over':
                    # Simple probability estimate: how often they exceed this line
                    exceed_count = sum(1 for v in values if v > line)
                    estimated_prob = exceed_count / len(values) if values else 0.5
                    # Adjust based on how close line is to average
                    if line < avg_value:
                        estimated_prob = max(0.5, min(0.95, estimated_prob + 0.2))
                    elif line > avg_value + std_dev:
                        estimated_prob = max(0.1, min(0.5, estimated_prob - 0.2))
                else:  # Under
                    exceed_count = sum(1 for v in values if v < line)
                    estimated_prob = exceed_count / len(values) if values else 0.5
                    if line > avg_value:
                        estimated_prob = max(0.5, min(0.95, estimated_prob + 0.2))
                    elif line < avg_value - std_dev:
                        estimated_prob = max(0.1, min(0.5, estimated_prob - 0.2))
            else:
                # No historical stats, use default probability
                estimated_prob = 0.5
                avg_value = line
                std_dev = line * 0.2
            
            # Find a game for today or upcoming
            if game_date:
                game = self.db.query(Game).filter(Game.game_date == game_date).first()
            else:
                # Find next game for this player's team
                from app.models.team import Team
                from datetime import date
                today = date.today()
                # Get player's team (simplified - you may need to adjust based on your schema)
                game = self.db.query(Game).filter(
                    Game.game_date >= today
                ).order_by(Game.game_date.asc()).first()
            
            if not game:
                # No game found - try to find a game for this player's team
                from datetime import date
                today = date.today()
                team_id = player.current_team_id
                if team_id:
                    game = self.db.query(Game).filter(
                        and_(
                            Game.game_date >= today,
                            or_(
                                Game.home_team_id == team_id,
                                Game.away_team_id == team_id
                            )
                        )
                    ).order_by(Game.game_date.asc()).first()
            
            if not game:
                # Still no game found - return None to indicate we can't match this bet
                return None
            
            game_id = game.game_id
            game_date_str = game.game_date.isoformat() if game.game_date else None
            
            # Return a match without a prediction_id (we'll create the play directly)
            return {
                'prediction_id': -1,  # Use -1 instead of None to indicate no prediction exists
                'player_id': player.player_id,
                'player_name': player.name,
                'game_id': game_id if game_id > 0 else None,  # Don't return 0, return None
                'game_date': game_date_str,
                'stat_type': stat_type,
                'bet_type': bet_type,
                'line': line,
                'bet_line': f'{bet_type} {line}',
                'prediction': None,
                'confidence': estimated_prob,
                'matched_line': line,
                'estimated_mean': avg_value,
                'estimated_std': std_dev
            }
        
        # Find the best matching prediction
        # Prefer predictions where the line is close to what user specified
        best_pred = None
        best_score = 0
        
        for pred in predictions:
            # Get the appropriate line based on bet_type
            pred_line = None
            if bet_type == 'Over':
                if pred.safe_line:
                    pred_line = pred.safe_line
                elif pred.standard_line:
                    pred_line = pred.standard_line
                elif pred.long_shot_line:
                    pred_line = pred.long_shot_line
            else:  # Under
                # For under, we'd need to calculate from distribution
                # For now, use mean as approximation
                pred_line = pred.distribution_mean
            
            if pred_line is None:
                continue
            
            # Score based on how close the line is
            line_diff = abs(pred_line - line)
            score = 1.0 / (1.0 + line_diff)  # Higher score for closer lines
            
            if score > best_score:
                best_score = score
                best_pred = pred
        
        if not best_pred:
            return None
        
        # Get game info
        game = self.db.query(Game).filter(Game.game_id == best_pred.game_id).first()
        
        return {
            'prediction_id': best_pred.prediction_id if best_pred else -1,
            'player_id': player.player_id,
            'player_name': player.name,
            'game_id': best_pred.game_id if best_pred else None,
            'game_date': game.game_date.isoformat() if game and game.game_date else None,
            'stat_type': stat_type,
            'bet_type': bet_type,
            'line': line,
            'bet_line': f'{bet_type} {line}',
            'prediction': best_pred,
            'confidence': best_score if best_pred else 0.5,
            'matched_line': (best_pred.safe_line or best_pred.standard_line or best_pred.long_shot_line) if best_pred else line
        }

