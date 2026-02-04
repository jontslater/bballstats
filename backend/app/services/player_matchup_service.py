"""
Player Matchup Service

Analyzes individual player vs player defensive matchups.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import Dict, List, Optional
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team
from app.models.player_team_matchup import PlayerTeamMatchup


class PlayerMatchupService:
    """Analyze individual player vs player matchups."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def find_defensive_matchup(
        self,
        offensive_player_id: int,
        opponent_team_id: int,
        position: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Find the most likely defensive matchup for a player.
        
        Uses position and recent lineup data to identify primary defender.
        
        Returns:
            Dict with matchup information
        """
        offensive_player = self.db.query(Player).filter(Player.player_id == offensive_player_id).first()
        if not offensive_player:
            return None
        
        # Get opponent team's players at the same position (likely defender)
        opponent_players = self.db.query(Player).filter(
            and_(
                Player.current_team_id == opponent_team_id,
                Player.position == (position or offensive_player.position)
            )
        ).all()
        
        if not opponent_players:
            return None
        
        # For now, return the primary defender (first player found)
        # In a full implementation, would analyze lineup data to find actual matchup
        primary_defender = opponent_players[0]
        
        return {
            'offensive_player_id': offensive_player_id,
            'offensive_player_name': offensive_player.name,
            'defender_id': primary_defender.player_id,
            'defender_name': primary_defender.name,
            'position': offensive_player.position,
            'confidence': 'LOW'  # Would be higher with actual lineup data
        }
    
    def analyze_player_vs_player_history(
        self,
        offensive_player_id: int,
        defender_player_id: int,
        season_id: Optional[int] = None
    ) -> Dict:
        """
        Analyze historical performance when these two players matched up.
        
        Returns:
            Dict with matchup statistics
        """
        from app.models.season import Season
        
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return {'error': 'No season found'}
            season_id = season.season_id
        
        # Find games where both players played
        # This is simplified - would need actual defensive assignment data
        offensive_games = self.db.query(Game).join(
            PlayerGameStat, Game.game_id == PlayerGameStat.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == offensive_player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        ).all()
        
        defender_games = self.db.query(Game).join(
            PlayerGameStat, Game.game_id == PlayerGameStat.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == defender_player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished'
            )
        ).all()
        
        # Find games where they played against each other
        offensive_game_ids = {g.game_id for g in offensive_games}
        defender_game_ids = {g.game_id for g in defender_games}
        matchup_game_ids = offensive_game_ids.intersection(defender_game_ids)
        
        if len(matchup_game_ids) < 3:
            return {
                'games_played': len(matchup_game_ids),
                'insufficient_data': True
            }
        
        # Get offensive player's stats in these games
        matchup_stats = self.db.query(PlayerGameStat).filter(
            and_(
                PlayerGameStat.player_id == offensive_player_id,
                PlayerGameStat.game_id.in_(list(matchup_game_ids))
            )
        ).all()
        
        if not matchup_stats:
            return {'error': 'No stats found'}
        
        # Calculate averages
        avg_points = sum(s.points or 0 for s in matchup_stats) / len(matchup_stats)
        avg_rebounds = sum(s.rebounds or 0 for s in matchup_stats) / len(matchup_stats)
        avg_assists = sum(s.assists or 0 for s in matchup_stats) / len(matchup_stats)
        avg_minutes = sum(s.minutes_played or 0 for s in matchup_stats) / len(matchup_stats)
        
        # Compare to season average
        all_season_stats = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == offensive_player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).all()
        
        if len(all_season_stats) >= 10:
            season_avg_points = sum(s.points or 0 for s in all_season_stats) / len(all_season_stats)
            season_avg_rebounds = sum(s.rebounds or 0 for s in all_season_stats) / len(all_season_stats)
            season_avg_assists = sum(s.assists or 0 for s in all_season_stats) / len(all_season_stats)
            
            # Calculate matchup factor
            points_factor = avg_points / season_avg_points if season_avg_points > 0 else 1.0
            rebounds_factor = avg_rebounds / season_avg_rebounds if season_avg_rebounds > 0 else 1.0
            assists_factor = avg_assists / season_avg_assists if season_avg_assists > 0 else 1.0
        else:
            points_factor = rebounds_factor = assists_factor = 1.0
            season_avg_points = season_avg_rebounds = season_avg_assists = None
        
        return {
            'games_played': len(matchup_stats),
            'avg_points': round(avg_points, 2),
            'avg_rebounds': round(avg_rebounds, 2),
            'avg_assists': round(avg_assists, 2),
            'avg_minutes': round(avg_minutes, 2),
            'season_avg_points': round(season_avg_points, 2) if season_avg_points else None,
            'points_factor': round(points_factor, 3),
            'rebounds_factor': round(rebounds_factor, 3),
            'assists_factor': round(assists_factor, 3),
            'matchup_advantage': 'POSITIVE' if points_factor > 1.05 else 'NEGATIVE' if points_factor < 0.95 else 'NEUTRAL'
        }
    
    def get_matchup_adjustment(
        self,
        offensive_player_id: int,
        opponent_team_id: int,
        stat_type: str,
        season_id: Optional[int] = None,
        offensive_streak_info: Optional[Dict] = None,
        defensive_streak_info: Optional[Dict] = None
    ) -> float:
        """
        Get matchup adjustment factor for a player vs team, enhanced with streak context.

        Args:
            offensive_player_id: Player attempting to score
            opponent_team_id: Team being defended against
            stat_type: Type of stat to analyze
            season_id: Season for analysis
            offensive_streak_info: Optional streak data for offensive player
            defensive_streak_info: Optional streak data for defender

        Returns:
            Adjustment factor (0.85 to 1.15)
        """
        matchup_info = self.find_defensive_matchup(offensive_player_id, opponent_team_id)

        if not matchup_info or matchup_info.get('confidence') == 'LOW':
            return 1.0  # No adjustment if uncertain

        defender_id = matchup_info.get('defender_id')
        if not defender_id:
            return 1.0

        history = self.analyze_player_vs_player_history(
            offensive_player_id, defender_id, season_id
        )

        if history.get('insufficient_data') or history.get('games_played', 0) < 3:
            return 1.0

        # Use appropriate factor based on stat type
        base_factor = 1.0
        if stat_type == 'points':
            base_factor = history.get('points_factor', 1.0)
        elif stat_type == 'rebounds':
            base_factor = history.get('rebounds_factor', 1.0)
        elif stat_type == 'assists':
            base_factor = history.get('assists_factor', 1.0)

        # ENHANCEMENT: Apply streak context multipliers
        streak_multiplier = 1.0

        # Offensive player streak context
        if offensive_streak_info:
            offensive_streak_type = offensive_streak_info.get('streak_type')
            offensive_streak_length = offensive_streak_info.get('streak_length', 0)

            if offensive_streak_type == 'hot' and offensive_streak_length >= 3:
                # Hot offensive player gets boost against this defender
                streak_multiplier *= 1.05
            elif offensive_streak_type == 'cold' and offensive_streak_length >= 3:
                # Cold offensive player gets penalty against this defender
                streak_multiplier *= 0.95

        # Defensive player streak context
        if defensive_streak_info:
            defensive_streak_type = defensive_streak_info.get('streak_type')
            defensive_streak_length = defensive_streak_info.get('streak_length', 0)

            if defensive_streak_type == 'cold' and defensive_streak_length >= 3:
                # Cold defender (allowing more stats) gives offensive boost
                streak_multiplier *= 1.03
            elif defensive_streak_type == 'hot' and defensive_streak_length >= 3:
                # Hot defender (allowing fewer stats) gives offensive penalty
                streak_multiplier *= 0.97

        # Special case: Hot offense vs Cold defense = big boost
        if (offensive_streak_info and offensive_streak_info.get('streak_type') == 'hot' and
            offensive_streak_info.get('streak_length', 0) >= 3 and
            defensive_streak_info and defensive_streak_info.get('streak_type') == 'cold' and
            defensive_streak_info.get('streak_length', 0) >= 3):
            streak_multiplier *= 1.07  # Additional 7% boost for perfect matchup

        # Apply streak context to base factor
        enhanced_factor = base_factor * streak_multiplier

        # Clamp to reasonable range (expanded for streak context)
        factor = max(0.85, min(1.15, enhanced_factor))

        return round(factor, 3)

    def get_comprehensive_matchup_analysis(
        self,
        offensive_player_id: int,
        opponent_team_id: int,
        stat_type: str,
        game_id: int,
        season_id: Optional[int] = None
    ) -> Dict[str, float]:
        """
        Comprehensive matchup analysis combining multiple factors.

        Args:
            offensive_player_id: Player attempting to score
            opponent_team_id: Team being defended against
            stat_type: Type of stat to analyze
            game_id: Current game ID
            season_id: Season for analysis

        Returns:
            Dict with comprehensive matchup factors
        """
        from app.models.game import Game
        from app.services.form_calculator import FormCalculator
        from app.services.game_context_calculator import GameContextCalculator

        # Get current game info
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return {'overall_matchup_factor': 1.0}

        # Initialize services
        form_calc = FormCalculator(self.db)
        game_context_calc = GameContextCalculator(self.db)

        # Factor 1: Individual Player vs Player Matchup
        individual_factor = self.get_matchup_adjustment(
            offensive_player_id, opponent_team_id, stat_type, season_id
        )

        # Factor 2: Team vs Team Defensive Matchup
        team_defensive_factor = self._calculate_team_defensive_matchup(
            offensive_player_id, opponent_team_id, stat_type, season_id
        )

        # Factor 3: Offensive vs Defensive Performance Trends
        trend_factor = self._calculate_matchup_trend_factor(
            offensive_player_id, opponent_team_id, stat_type, season_id
        )

        # Factor 4: Home/Away Context
        home_away_factor = self._calculate_home_away_matchup_factor(
            offensive_player_id, opponent_team_id, stat_type, game, season_id
        )

        # Factor 5: Rest and Fatigue Context
        rest_factor = self._calculate_rest_matchup_factor(
            offensive_player_id, opponent_team_id, game, season_id
        )

        # Factor 6: Recent Matchup History (weighted more heavily)
        recent_history_factor = self._calculate_recent_matchup_history(
            offensive_player_id, opponent_team_id, stat_type, season_id, last_n_games=5
        )

        # Weighted combination of all factors
        weights = {
            'individual': 0.25,      # Player vs player matchup
            'team_defensive': 0.20,  # Team defensive strength
            'trend': 0.15,           # Performance trends
            'home_away': 0.15,       # Home/away context
            'rest': 0.10,            # Rest/fatigue
            'recent_history': 0.15   # Recent matchup history
        }

        overall_factor = (
            individual_factor * weights['individual'] +
            team_defensive_factor * weights['team_defensive'] +
            trend_factor * weights['trend'] +
            home_away_factor * weights['home_away'] +
            rest_factor * weights['rest'] +
            recent_history_factor * weights['recent_history']
        )

        # Normalize to ensure the weighted average is properly scaled
        total_weight = sum(weights.values())
        overall_factor = overall_factor / total_weight

        return {
            'overall_matchup_factor': round(overall_factor, 3),
            'individual_factor': round(individual_factor, 3),
            'team_defensive_factor': round(team_defensive_factor, 3),
            'trend_factor': round(trend_factor, 3),
            'home_away_factor': round(home_away_factor, 3),
            'rest_factor': round(rest_factor, 3),
            'recent_history_factor': round(recent_history_factor, 3)
        }

    def _calculate_team_defensive_matchup(
        self,
        player_id: int,
        opponent_team_id: int,
        stat_type: str,
        season_id: Optional[int] = None
    ) -> float:
        """Calculate team-level defensive matchup factor."""
        # Simplified: use league average adjustments
        # In a full implementation, would analyze team defensive stats
        return 1.0  # Placeholder

    def _calculate_matchup_trend_factor(
        self,
        player_id: int,
        opponent_team_id: int,
        stat_type: str,
        season_id: Optional[int] = None
    ) -> float:
        """Calculate trend-based matchup factor."""
        # Simplified: analyze recent performance vs this opponent
        matchup = self.db.query(PlayerTeamMatchup).filter(
            and_(
                PlayerTeamMatchup.player_id == player_id,
                PlayerTeamMatchup.opponent_team_id == opponent_team_id
            )
        ).first()

        if matchup and matchup.last_5_games_avg_points:
            # Compare recent matchup performance to season average
            base_avg = getattr(matchup, f'avg_{stat_type}', 0)
            recent_avg = getattr(matchup, f'last_5_games_avg_{stat_type}', 0)

            if base_avg > 0 and recent_avg > 0:
                trend_factor = recent_avg / base_avg
                return max(0.85, min(1.15, trend_factor))

        return 1.0

    def _calculate_home_away_matchup_factor(
        self,
        player_id: int,
        opponent_team_id: int,
        stat_type: str,
        game,
        season_id: Optional[int] = None
    ) -> float:
        """Calculate home/away context for matchup."""
        # Simplified: players perform better at home
        is_home = game.home_team_id == getattr(game, 'home_team_id', None)  # Get player's team
        base_factor = 1.05 if is_home else 0.95

        # Could be enhanced with home/away vs specific opponents
        return base_factor

    def _calculate_rest_matchup_factor(
        self,
        player_id: int,
        opponent_team_id: int,
        game,
        season_id: Optional[int] = None
    ) -> float:
        """Calculate rest/fatigue impact on matchup."""
        # Simplified: analyze back-to-back games
        # In full implementation, would check rest days
        return 1.0  # Placeholder

    def _calculate_recent_matchup_history(
        self,
        player_id: int,
        opponent_team_id: int,
        stat_type: str,
        season_id: Optional[int] = None,
        last_n_games: int = 5
    ) -> float:
        """Calculate recent matchup history factor."""
        # Get recent games vs this opponent
        recent_stats = self.db.query(PlayerGameStat).join(Game).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.away_team_id == opponent_team_id,
                Game.season_id == season_id
            )
        ).order_by(desc(Game.game_date)).limit(last_n_games).all()

        if not recent_stats:
            return 1.0

        # Calculate average performance in recent matchups
        values = []
        for stat in recent_stats:
            if stat_type == 'points':
                values.append(stat.points or 0)
            elif stat_type == 'rebounds':
                values.append(stat.rebounds or 0)
            elif stat_type == 'assists':
                values.append(stat.assists or 0)
            elif stat_type == 'three_pointers_made':
                values.append(stat.three_pointers_made or 0)

        if values:
            recent_avg = sum(values) / len(values)

            # Compare to player's season average
            season_stats = self.db.query(PlayerGameStat).join(Game).filter(
                and_(
                    PlayerGameStat.player_id == player_id,
                    Game.season_id == season_id
                )
            ).all()

            season_values = []
            for stat in season_stats:
                if stat_type == 'points':
                    season_values.append(stat.points or 0)
                elif stat_type == 'rebounds':
                    season_values.append(stat.rebounds or 0)
                elif stat_type == 'assists':
                    season_values.append(stat.assists or 0)
                elif stat_type == 'three_pointers_made':
                    season_values.append(stat.three_pointers_made or 0)

            if season_values:
                season_avg = sum(season_values) / len(season_values)
                if season_avg > 0:
                    history_factor = recent_avg / season_avg
                    return max(0.85, min(1.15, history_factor))

        return 1.0

