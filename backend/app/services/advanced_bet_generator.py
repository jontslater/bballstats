"""
Advanced Bet Generator

Generates additional bet types beyond basic Over/Under:
- Combo props (Points + Rebounds, etc.)
- Milestone props (20+ points, double-double, triple-double)
- Player vs Player props
- Alternate lines
- Performance brackets
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from typing import List, Dict, Optional
from datetime import date
from scipy.stats import norm
from app.models.prediction import Prediction
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team
from app.models.player_game_stat import PlayerGameStat


class AdvancedBetGenerator:
    """Generate advanced bet types."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_combo_props(
        self,
        game_id: int,
        player_id: int,
        combo_type: str = "points_rebounds"  # "points_rebounds", "points_assists", "rebounds_assists"
    ) -> List[Dict]:
        """
        Generate combo prop bets (e.g., Points + Rebounds Over X).
        
        Returns:
            List of combo prop dictionaries
        """
        # Get predictions for both stats
        if combo_type == "points_rebounds":
            stat1 = "points"
            stat2 = "rebounds"
        elif combo_type == "points_assists":
            stat1 = "points"
            stat2 = "assists"
        elif combo_type == "rebounds_assists":
            stat1 = "rebounds"
            stat2 = "assists"
        else:
            return []
        
        pred1 = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id == game_id,
                Prediction.player_id == player_id,
                Prediction.stat_type == stat1,
                Prediction.bet_type.in_(['safe', 'standard'])
            )
        ).first()
        
        pred2 = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id == game_id,
                Prediction.player_id == player_id,
                Prediction.stat_type == stat2,
                Prediction.bet_type.in_(['safe', 'standard'])
            )
        ).first()
        
        if not pred1 or not pred2:
            return []
        
        # Combine distributions (sum of two normal distributions)
        # Mean of sum = mean1 + mean2
        # Variance of sum = var1 + var2 (assuming independence)
        combined_mean = pred1.distribution_mean + pred2.distribution_mean
        combined_std = (pred1.distribution_std_dev ** 2 + pred2.distribution_std_dev ** 2) ** 0.5
        
        # Create combined distribution
        dist = norm(loc=combined_mean, scale=combined_std)
        
        # Get player info
        player = self.db.query(Player).filter(Player.player_id == player_id).first()
        player_name = player.name if player else f"Player {player_id}"
        
        # Generate bet lines
        combo_bets = []
        
        # Safe combo (25th percentile)
        safe_line = combined_mean * 0.90  # Conservative
        safe_prob = float(1.0 - dist.cdf(safe_line))
        if safe_prob >= 0.70:
            combo_bets.append({
                'player_id': player_id,
                'player_name': player_name,
                'combo_type': combo_type,
                'stat1': stat1,
                'stat2': stat2,
                'line': round(safe_line, 1),
                'probability': round(safe_prob, 3),
                'bet_type': 'safe',
                'display': f"{player_name}: {stat1.capitalize()} + {stat2.capitalize()} Over {safe_line:.1f}"
            })
        
        # Standard combo (50th percentile)
        standard_line = combined_mean
        standard_prob = float(1.0 - dist.cdf(standard_line))
        if standard_prob >= 0.45:
            combo_bets.append({
                'player_id': player_id,
                'player_name': player_name,
                'combo_type': combo_type,
                'stat1': stat1,
                'stat2': stat2,
                'line': round(standard_line, 1),
                'probability': round(standard_prob, 3),
                'bet_type': 'standard',
                'display': f"{player_name}: {stat1.capitalize()} + {stat2.capitalize()} Over {standard_line:.1f}"
            })
        
        # Long shot combo (85th percentile)
        long_shot_line = combined_mean * 1.15
        long_shot_prob = float(1.0 - dist.cdf(long_shot_line))
        if 0.08 <= long_shot_prob <= 0.30:
            combo_bets.append({
                'player_id': player_id,
                'player_name': player_name,
                'combo_type': combo_type,
                'stat1': stat1,
                'stat2': stat2,
                'line': round(long_shot_line, 1),
                'probability': round(long_shot_prob, 3),
                'bet_type': 'long_shot',
                'display': f"{player_name}: {stat1.capitalize()} + {stat2.capitalize()} Over {long_shot_line:.1f}"
            })
        
        return combo_bets
    
    def generate_milestone_props(
        self,
        game_id: int,
        player_id: int
    ) -> List[Dict]:
        """
        Generate milestone prop bets (20+ points, 10+ rebounds, double-double, triple-double).
        
        Returns:
            List of milestone prop dictionaries
        """
        # Get player info
        player = self.db.query(Player).filter(Player.player_id == player_id).first()
        player_name = player.name if player else f"Player {player_id}"
        
        # Get all stat predictions for this player/game
        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id == game_id,
                Prediction.player_id == player_id,
                Prediction.stat_type.in_(['points', 'rebounds', 'assists']),
                Prediction.bet_type.in_(['safe', 'standard'])
            )
        ).all()
        
        if len(predictions) < 3:  # Need points, rebounds, assists
            return []
        
        pred_dict = {p.stat_type: p for p in predictions}
        
        milestone_bets = []
        
        # Points milestones
        if 'points' in pred_dict:
            points_pred = pred_dict['points']
            dist = norm(loc=points_pred.distribution_mean, scale=points_pred.distribution_std_dev)
            
            milestones = [
                (15, "15+ Points"),
                (20, "20+ Points"),
                (25, "25+ Points"),
                (30, "30+ Points"),
                (35, "35+ Points")
            ]
            
            for threshold, label in milestones:
                prob = float(1.0 - dist.cdf(threshold))
                if 0.20 <= prob <= 0.80:  # Reasonable probability range
                    milestone_bets.append({
                        'player_id': player_id,
                        'player_name': player_name,
                        'type': 'points_milestone',
                        'milestone': threshold,
                        'label': label,
                        'probability': round(prob, 3),
                        'bet_type': 'milestone',
                        'display': f"{player_name}: {label}"
                    })
        
        # Rebounds milestones
        if 'rebounds' in pred_dict:
            rebounds_pred = pred_dict['rebounds']
            dist = norm(loc=rebounds_pred.distribution_mean, scale=rebounds_pred.distribution_std_dev)
            
            milestones = [
                (5, "5+ Rebounds"),
                (10, "10+ Rebounds"),
                (15, "15+ Rebounds"),
                (20, "20+ Rebounds")
            ]
            
            for threshold, label in milestones:
                prob = float(1.0 - dist.cdf(threshold))
                if 0.20 <= prob <= 0.80:
                    milestone_bets.append({
                        'player_id': player_id,
                        'player_name': player_name,
                        'type': 'rebounds_milestone',
                        'milestone': threshold,
                        'label': label,
                        'probability': round(prob, 3),
                        'bet_type': 'milestone',
                        'display': f"{player_name}: {label}"
                    })
        
        # Assists milestones
        if 'assists' in pred_dict:
            assists_pred = pred_dict['assists']
            dist = norm(loc=assists_pred.distribution_mean, scale=assists_pred.distribution_std_dev)
            
            milestones = [
                (5, "5+ Assists"),
                (10, "10+ Assists"),
                (15, "15+ Assists")
            ]
            
            for threshold, label in milestones:
                prob = float(1.0 - dist.cdf(threshold))
                if 0.20 <= prob <= 0.80:
                    milestone_bets.append({
                        'player_id': player_id,
                        'player_name': player_name,
                        'type': 'assists_milestone',
                        'milestone': threshold,
                        'label': label,
                        'probability': round(prob, 3),
                        'bet_type': 'milestone',
                        'display': f"{player_name}: {label}"
                    })
        
        # Double-double (10+ in two categories)
        if all(s in pred_dict for s in ['points', 'rebounds']):
            dd_prob = self._calculate_double_double_probability(
                pred_dict['points'], pred_dict['rebounds']
            )
            if dd_prob >= 0.15:  # At least 15% chance
                milestone_bets.append({
                    'player_id': player_id,
                    'player_name': player_name,
                    'type': 'double_double',
                    'label': "Double-Double (10+ Points & 10+ Rebounds)",
                    'probability': round(dd_prob, 3),
                    'bet_type': 'milestone',
                    'display': f"{player_name}: Double-Double"
                })
        
        # Triple-double (10+ in three categories)
        if all(s in pred_dict for s in ['points', 'rebounds', 'assists']):
            td_prob = self._calculate_triple_double_probability(
                pred_dict['points'], pred_dict['rebounds'], pred_dict['assists']
            )
            if td_prob >= 0.05:  # At least 5% chance
                milestone_bets.append({
                    'player_id': player_id,
                    'player_name': player_name,
                    'type': 'triple_double',
                    'label': "Triple-Double (10+ Points, 10+ Rebounds, 10+ Assists)",
                    'probability': round(td_prob, 3),
                    'bet_type': 'milestone',
                    'display': f"{player_name}: Triple-Double"
                })
        
        return milestone_bets
    
    def _calculate_double_double_probability(
        self,
        pred1: Prediction,
        pred2: Prediction
    ) -> float:
        """Calculate probability of double-double (10+ in both stats)."""
        # Simplified: assume independence
        dist1 = norm(loc=pred1.distribution_mean, scale=pred1.distribution_std_dev)
        dist2 = norm(loc=pred2.distribution_mean, scale=pred2.distribution_std_dev)
        
        prob1 = float(1.0 - dist1.cdf(10))
        prob2 = float(1.0 - dist2.cdf(10))
        
        # Joint probability (assuming independence)
        return prob1 * prob2
    
    def _calculate_triple_double_probability(
        self,
        pred1: Prediction,
        pred2: Prediction,
        pred3: Prediction
    ) -> float:
        """Calculate probability of triple-double (10+ in all three stats)."""
        dist1 = norm(loc=pred1.distribution_mean, scale=pred1.distribution_std_dev)
        dist2 = norm(loc=pred2.distribution_mean, scale=pred2.distribution_std_dev)
        dist3 = norm(loc=pred3.distribution_mean, scale=pred3.distribution_std_dev)
        
        prob1 = float(1.0 - dist1.cdf(10))
        prob2 = float(1.0 - dist2.cdf(10))
        prob3 = float(1.0 - dist3.cdf(10))
        
        # Joint probability (assuming independence)
        return prob1 * prob2 * prob3
    
    def generate_player_vs_player_props(
        self,
        game_id: int,
        player1_id: int,
        player2_id: int,
        stat_type: str = "points"
    ) -> Optional[Dict]:
        """
        Generate player vs player prop (Player A points vs Player B points).
        
        Returns:
            Player vs player prop dictionary
        """
        pred1 = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id == game_id,
                Prediction.player_id == player1_id,
                Prediction.stat_type == stat_type,
                Prediction.bet_type.in_(['safe', 'standard'])
            )
        ).first()
        
        pred2 = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id == game_id,
                Prediction.player_id == player2_id,
                Prediction.stat_type == stat_type,
                Prediction.bet_type.in_(['safe', 'standard'])
            )
        ).first()
        
        if not pred1 or not pred2:
            return None
        
        player1 = self.db.query(Player).filter(Player.player_id == player1_id).first()
        player2 = self.db.query(Player).filter(Player.player_id == player2_id).first()
        
        # Calculate difference distribution
        # Mean difference = mean1 - mean2
        # Variance of difference = var1 + var2 (assuming independence)
        diff_mean = pred1.distribution_mean - pred2.distribution_mean
        diff_std = (pred1.distribution_std_dev ** 2 + pred2.distribution_std_dev ** 2) ** 0.5
        
        dist = norm(loc=diff_mean, scale=diff_std)
        
        # Probability that player1 > player2
        prob_player1_wins = float(1.0 - dist.cdf(0))
        
        # Probability that player1 wins by 5+ points
        prob_player1_wins_by_5 = float(1.0 - dist.cdf(5))
        
        return {
            'player1_id': player1_id,
            'player1_name': player1.name if player1 else f"Player {player1_id}",
            'player2_id': player2_id,
            'player2_name': player2.name if player2 else f"Player {player2_id}",
            'stat_type': stat_type,
            'expected_difference': round(diff_mean, 2),
            'player1_win_probability': round(prob_player1_wins, 3),
            'player1_win_by_5_probability': round(prob_player1_wins_by_5, 3),
            'display': f"{player1.name if player1 else f'Player {player1_id}'} vs {player2.name if player2 else f'Player {player2_id}'} ({stat_type})"
        }
    
    def generate_alternate_lines(
        self,
        game_id: int,
        player_id: int,
        stat_type: str
    ) -> List[Dict]:
        """
        Generate alternate line options (multiple Over/Under options).
        
        Returns:
            List of alternate line dictionaries
        """
        prediction = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id == game_id,
                Prediction.player_id == player_id,
                Prediction.stat_type == stat_type,
                Prediction.bet_type.in_(['safe', 'standard', 'long_shot'])
            )
        ).first()
        
        if not prediction:
            return []
        
        dist = norm(loc=prediction.distribution_mean, scale=prediction.distribution_std_dev)
        
        alternate_lines = []
        
        # Generate lines at different percentiles
        percentiles = [10, 20, 25, 30, 40, 50, 60, 70, 75, 80, 85, 90]
        
        for pct in percentiles:
            line = getattr(prediction, f'percentile_{pct}', None)
            if line is None:
                # Calculate from distribution
                line = dist.ppf(pct / 100.0)
            
            prob = float(1.0 - dist.cdf(line))
            
            # Only include reasonable probabilities
            if 0.10 <= prob <= 0.90:
                alternate_lines.append({
                    'line': round(line, 1),
                    'probability': round(prob, 3),
                    'percentile': pct,
                    'display': f"Over {line:.1f}",
                    'odds_estimate': self._probability_to_odds(prob)
                })
        
        # Sort by probability (highest first)
        alternate_lines.sort(key=lambda x: x['probability'], reverse=True)
        
        return alternate_lines
    
    def _probability_to_odds(self, prob: float) -> str:
        """Convert probability to American odds estimate."""
        if prob >= 0.5:
            # Favorite (negative odds)
            decimal_odds = 1.0 / prob
            american_odds = (decimal_odds - 1) * 100
            return f"-{int(american_odds)}"
        else:
            # Underdog (positive odds)
            decimal_odds = 1.0 / prob
            american_odds = (decimal_odds - 1) * 100
            return f"+{int(american_odds)}"
    
    def generate_performance_brackets(
        self,
        game_id: int,
        player_id: int,
        stat_type: str
    ) -> List[Dict]:
        """
        Generate performance bracket bets (e.g., 15-20 points, 20-25 points).
        
        Returns:
            List of bracket dictionaries
        """
        prediction = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id == game_id,
                Prediction.player_id == player_id,
                Prediction.stat_type == stat_type,
                Prediction.bet_type.in_(['safe', 'standard'])
            )
        ).first()
        
        if not prediction:
            return []
        
        dist = norm(loc=prediction.distribution_mean, scale=prediction.distribution_std_dev)
        
        brackets = []
        
        # Define brackets based on stat type
        if stat_type == 'points':
            bracket_ranges = [
                (0, 10, "0-10 Points"),
                (10, 15, "10-15 Points"),
                (15, 20, "15-20 Points"),
                (20, 25, "20-25 Points"),
                (25, 30, "25-30 Points"),
                (30, 35, "30-35 Points"),
                (35, 100, "35+ Points")
            ]
        elif stat_type == 'rebounds':
            bracket_ranges = [
                (0, 5, "0-5 Rebounds"),
                (5, 10, "5-10 Rebounds"),
                (10, 15, "10-15 Rebounds"),
                (15, 20, "15-20 Rebounds"),
                (20, 100, "20+ Rebounds")
            ]
        elif stat_type == 'assists':
            bracket_ranges = [
                (0, 5, "0-5 Assists"),
                (5, 10, "5-10 Assists"),
                (10, 15, "10-15 Assists"),
                (15, 100, "15+ Assists")
            ]
        else:
            return []
        
        for min_val, max_val, label in bracket_ranges:
            # Calculate probability of being in this range
            prob = float(dist.cdf(max_val) - dist.cdf(min_val))
            
            if prob >= 0.10:  # At least 10% probability
                brackets.append({
                    'min': min_val,
                    'max': max_val,
                    'label': label,
                    'probability': round(prob, 3),
                    'bet_type': 'bracket',
                    'display': label
                })
        
        # Sort by probability (highest first)
        brackets.sort(key=lambda x: x['probability'], reverse=True)
        
        return brackets
    
    def generate_team_total_props(
        self,
        game_id: int,
        team_id: int,
        stat_type: str = "points"
    ) -> Optional[Dict]:
        """
        Generate team total prop (team total points/rebounds/assists).
        
        Returns:
            Team total prop dictionary
        """
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return None
        
        # Get all players on the team
        players = self.db.query(Player).filter(
            Player.current_team_id == team_id
        ).all()
        
        if not players:
            return None
        
        player_ids = [p.player_id for p in players]
        
        # Get predictions for all players
        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.game_id == game_id,
                Prediction.player_id.in_(player_ids),
                Prediction.stat_type == stat_type,
                Prediction.bet_type.in_(['safe', 'standard'])
            )
        ).all()
        
        if len(predictions) < 5:  # Need at least 5 players
            return None
        
        # Sum all player predictions (team total)
        # Mean of sum = sum of means
        # Variance of sum = sum of variances (assuming independence)
        team_mean = sum(p.distribution_mean for p in predictions)
        team_std = (sum(p.distribution_std_dev ** 2 for p in predictions)) ** 0.5
        
        dist = norm(loc=team_mean, scale=team_std)
        
        # Generate team total lines
        team = self.db.query(Team).filter(Team.team_id == team_id).first()
        
        # Standard lines
        lines = []
        if stat_type == 'points':
            # Common team total lines: 100, 105, 110, 115, 120, 125, 130
            common_lines = [100, 105, 110, 115, 120, 125, 130]
        elif stat_type == 'rebounds':
            common_lines = [40, 45, 50, 55, 60]
        elif stat_type == 'assists':
            common_lines = [20, 25, 30, 35, 40]
        else:
            return None
        
        for line in common_lines:
            prob_over = float(1.0 - dist.cdf(line))
            prob_under = float(dist.cdf(line))
            
            if 0.20 <= prob_over <= 0.80:  # Reasonable probability
                lines.append({
                    'line': line,
                    'over_probability': round(prob_over, 3),
                    'under_probability': round(prob_under, 3),
                    'over_odds': self._probability_to_odds(prob_over),
                    'under_odds': self._probability_to_odds(prob_under)
                })
        
        return {
            'team_id': team_id,
            'team_name': team.name if team else f"Team {team_id}",
            'stat_type': stat_type,
            'expected_total': round(team_mean, 1),
            'lines': lines,
            'display': f"{team.name if team else f'Team {team_id}'} Total {stat_type.capitalize()}"
        }
    
    def get_all_advanced_bets_for_game(
        self,
        game_id: int,
        limit_per_type: int = 5
    ) -> Dict[str, List[Dict]]:
        """
        Get all advanced bet types for a game.
        
        Returns:
            Dict with all bet types
        """
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return {}
        
        # Get all players in the game
        home_players = self.db.query(Player).filter(
            Player.current_team_id == game.home_team_id
        ).all()
        away_players = self.db.query(Player).filter(
            Player.current_team_id == game.away_team_id
        ).all()
        
        all_players = home_players + away_players
        
        result = {
            'combo_props': [],
            'milestone_props': [],
            'player_vs_player': [],
            'alternate_lines': [],
            'performance_brackets': [],
            'team_totals': [],
            'double_doubles': [],  # NEW: Players likely to get double-double
            'triple_doubles': []  # NEW: Players likely to get triple-double
        }
        
        # Generate combo props for top players
        for player in all_players[:10]:  # Top 10 players
            for combo_type in ["points_rebounds", "points_assists", "rebounds_assists"]:
                combo_bets = self.generate_combo_props(game_id, player.player_id, combo_type)
                result['combo_props'].extend(combo_bets[:limit_per_type])
        
        # Generate milestone props and track double/triple doubles
        for player in all_players[:15]:  # Top 15 players
            milestone_bets = self.generate_milestone_props(game_id, player.player_id)
            result['milestone_props'].extend(milestone_bets[:limit_per_type])
            
            # Extract double-doubles and triple-doubles
            for bet in milestone_bets:
                if bet.get('type') == 'double_double':
                    result['double_doubles'].append(bet)
                elif bet.get('type') == 'triple_double':
                    result['triple_doubles'].append(bet)
        
        # Generate player vs player (top players from each team)
        top_home = home_players[:3] if len(home_players) >= 3 else home_players
        top_away = away_players[:3] if len(away_players) >= 3 else away_players
        
        for p1 in top_home:
            for p2 in top_away:
                for stat_type in ["points", "rebounds", "assists"]:
                    pvp = self.generate_player_vs_player_props(game_id, p1.player_id, p2.player_id, stat_type)
                    if pvp:
                        result['player_vs_player'].append(pvp)
        
        # Generate alternate lines for top players
        for player in all_players[:10]:
            for stat_type in ["points", "rebounds", "assists"]:
                alt_lines = self.generate_alternate_lines(game_id, player.player_id, stat_type)
                result['alternate_lines'].extend(alt_lines[:3])  # Top 3 alternate lines per player
        
        # Generate performance brackets
        for player in all_players[:10]:
            for stat_type in ["points", "rebounds", "assists"]:
                brackets = self.generate_performance_brackets(game_id, player.player_id, stat_type)
                result['performance_brackets'].extend(brackets[:2])  # Top 2 brackets per player
        
        # Generate team totals
        for team_id in [game.home_team_id, game.away_team_id]:
            for stat_type in ["points", "rebounds", "assists"]:
                team_total = self.generate_team_total_props(game_id, team_id, stat_type)
                if team_total:
                    result['team_totals'].append(team_total)
        
        # Sort and limit results
        for key in result:
            if key == 'player_vs_player':
                # Sort by probability difference
                result[key].sort(key=lambda x: abs(x.get('expected_difference', 0)), reverse=True)
            elif key == 'team_totals':
                # Already limited
                pass
            elif key in ['double_doubles', 'triple_doubles']:
                # Sort by probability (highest first)
                result[key].sort(key=lambda x: x.get('probability', 0), reverse=True)
                result[key] = result[key][:limit_per_type]  # Limit to top N
            else:
                # Sort by probability (highest first)
                result[key].sort(key=lambda x: x.get('probability', 0), reverse=True)
                result[key] = result[key][:limit_per_type * 5]  # Limit total
        
        return result

