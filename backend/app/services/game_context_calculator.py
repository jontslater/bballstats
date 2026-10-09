"""
Game Context Calculator

Calculates rest days, travel impact, and blowout risk for games.
"""
from sqlalchemy import and_, or_, desc
from sqlalchemy.orm import Session
from datetime import date, timedelta
from typing import Dict, Optional
from app.models.game import Game
from app.models.team import Team


class GameContextCalculator:
    """Calculate game context factors."""
    
    def __init__(self, db: Session):
        self.db = db
        self._context_cache: Dict[tuple, Dict] = {}
    
    def calculate_rest_days(
        self,
        team_id: int,
        game_date: date
    ) -> int:
        """
        Calculate rest days for a team before a game.
        
        Returns:
            Number of rest days (0 = back-to-back, 1 = 1 day rest, etc.)
        """
        # Get team's previous game
        previous_game = self.db.query(Game).filter(
            and_(
                or_(
                    Game.home_team_id == team_id,
                    Game.away_team_id == team_id
                ),
                Game.game_date < game_date,
                Game.game_status == 'finished'
            )
        ).order_by(desc(Game.game_date)).first()
        
        if not previous_game:
            # No previous game found, assume normal rest
            return 1
        
        rest_days = (game_date - previous_game.game_date).days - 1
        return max(0, rest_days)
    
    def calculate_rest_days_factor(self, rest_days: int) -> float:
        """
        Calculate adjustment factor based on rest days.
        
        Returns:
            Multiplier for stats (0.95 for back-to-back, 1.0 for 1 day, 1.02 for 2+ days)
        """
        if rest_days == 0:  # Back-to-back
            return 0.95
        elif rest_days == 1:  # 1 day rest
            return 1.0
        else:  # 2+ days rest
            return 1.02
    
    def calculate_travel_impact(
        self,
        team_id: int,
        game_id: int
    ) -> Dict[str, any]:
        """
        Calculate travel impact for a team.
        
        Returns:
            Dict with travel distance, time zone change, and impact factor
        """
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return {'travel_factor': 1.0}
        
        # Determine if team is home or away
        is_home = (game.home_team_id == team_id)
        
        if is_home:
            # No travel for home team
            return {
                'travel_distance': 0,
                'time_zone_change': 0,
                'travel_factor': 1.0
            }
        
        # For away team, would need to calculate distance between cities
        # This is simplified - would need team city/arena data
        # For now, assume minimal travel impact
        return {
            'travel_distance': 0,  # Would calculate from team locations
            'time_zone_change': 0,  # Would calculate from team time zones
            'travel_factor': 0.98  # Slight negative impact for away games
        }
    
    def calculate_blowout_risk(
        self,
        game_id: int,
        point_spread: Optional[float] = None
    ) -> Dict[str, any]:
        """
        Calculate blowout risk for a game.
        
        Considers:
        - Point spread (if available)
        - Team strength differences
        - Recent form
        - Key injuries
        
        Args:
            game_id: Game ID
            point_spread: Point spread (if available)
        
        Returns:
            Dict with blowout_risk_high (bool), risk_level (str), and risk_score (float 0-1)
        """
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return {
                'blowout_risk_high': False,
                'risk_level': 'LOW',
                'risk_score': 0.0,
                'point_spread': point_spread
            }
        
        risk_score = 0.0
        risk_factors = []
        
        # Factor 1: Point spread (if available) - strongest indicator
        if point_spread:
            abs_spread = abs(point_spread)
            if abs_spread >= 15:
                risk_score += 0.6
                risk_factors.append(f"Large point spread ({point_spread:+.1f})")
            elif abs_spread >= 10:
                risk_score += 0.4
                risk_factors.append(f"Moderate point spread ({point_spread:+.1f})")
            elif abs_spread >= 7:
                risk_score += 0.2
                risk_factors.append(f"Modest point spread ({point_spread:+.1f})")
        
        # Factor 2: Team strength difference (using recent win rates)
        from app.models.player_game_stat import PlayerGameStat
        from datetime import date, timedelta
        from sqlalchemy import func
        
        thirty_days_ago = date.today() - timedelta(days=30)
        
        # Get recent win rates for both teams
        for team_id in [game.home_team_id, game.away_team_id]:
            recent_games = self.db.query(Game).filter(
                and_(
                    or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
                    Game.game_date >= thirty_days_ago,
                    Game.game_status == 'finished'
                )
            ).limit(10).all()
            
            if recent_games:
                wins = sum(1 for g in recent_games if 
                          g.home_score is not None and g.away_score is not None and
                          ((g.home_team_id == team_id and g.home_score > g.away_score) or
                           (g.away_team_id == team_id and g.away_score > g.home_score)))
                valid_games = sum(1 for g in recent_games if g.home_score is not None and g.away_score is not None)
                if valid_games > 0:
                    win_rate = wins / valid_games
                    # Store for comparison
                    if team_id == game.home_team_id:
                        home_win_rate = win_rate
                    else:
                        away_win_rate = win_rate
        
        # Calculate win rate difference
        if 'home_win_rate' in locals() and 'away_win_rate' in locals():
            win_rate_diff = abs(home_win_rate - away_win_rate)
            if win_rate_diff >= 0.3:  # 30%+ difference
                risk_score += 0.3
                risk_factors.append(f"Large team strength difference ({win_rate_diff:.1%})")
            elif win_rate_diff >= 0.2:  # 20%+ difference
                risk_score += 0.15
                risk_factors.append(f"Moderate team strength difference ({win_rate_diff:.1%})")
        
        # Factor 3: Key injuries (if multiple key players out, blowout more likely)
        from app.services.injury_context import InjuryContext
        from app.models.injury import Injury
        from app.models.player import Player
        
        injury_context = InjuryContext(self.db)
        
        key_injuries_count = 0
        for team_id in [game.home_team_id, game.away_team_id]:
            # Count "Out" injuries for this team
            team_players = self.db.query(Player.player_id).filter(
                Player.current_team_id == team_id
            ).subquery()
            
            injuries = self.db.query(Injury).filter(
                and_(
                    Injury.player_id.in_(self.db.query(team_players.c.player_id)),
                    Injury.status == 'Out'
                )
            ).count()
            key_injuries_count += injuries
        
        if key_injuries_count >= 3:
            risk_score += 0.2
            risk_factors.append(f"Multiple key injuries ({key_injuries_count} players out)")
        elif key_injuries_count >= 2:
            risk_score += 0.1
            risk_factors.append(f"Some key injuries ({key_injuries_count} players out)")
        
        # Cap risk score at 1.0
        risk_score = min(1.0, risk_score)
        
        # Determine risk level
        if risk_score >= 0.6:
            risk_level = 'HIGH'
            blowout_risk_high = True
        elif risk_score >= 0.4:
            risk_level = 'MEDIUM'
            blowout_risk_high = False
        else:
            risk_level = 'LOW'
            blowout_risk_high = False
        
        return {
            'blowout_risk_high': blowout_risk_high,
            'risk_level': risk_level,
            'risk_score': round(risk_score, 2),
            'point_spread': point_spread,
            'risk_factors': risk_factors
        }
    
    def calculate_relative_rest_advantage(
        self,
        game_id: int,
        team_id: int
    ) -> float:
        """
        Calculate relative rest advantage (our rest vs opponent rest).
        
        Returns:
            Adjustment factor (0.97 to 1.03)
        """
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return 1.0
        
        our_rest = self.calculate_rest_days(team_id, game.game_date)
        opponent_team_id = game.away_team_id if game.home_team_id == team_id else game.home_team_id
        opponent_rest = self.calculate_rest_days(opponent_team_id, game.game_date)
        
        rest_difference = our_rest - opponent_rest
        
        # If we have 2+ days more rest: +2-3% boost
        if rest_difference >= 2:
            return 1.02
        # If we have 1 day more rest: +1% boost
        elif rest_difference == 1:
            return 1.01
        # If opponent has 2+ days more rest: -2-3% penalty
        elif rest_difference <= -2:
            return 0.98
        # If opponent has 1 day more rest: -1% penalty
        elif rest_difference == -1:
            return 0.99
        # Equal rest
        else:
            return 1.0
    
    def calculate_team_recent_performance(
        self,
        team_id: int,
        game_date: date,
        last_n_games: int = 10
    ) -> Dict[str, any]:
        """
        Calculate team's recent performance (win/loss record, point differential).
        
        Returns:
            Dict with win_pct, point_differential, and adjustment factor
        """
        # Get team's last N finished games before this game
        recent_games = self.db.query(Game).filter(
            and_(
                or_(
                    Game.home_team_id == team_id,
                    Game.away_team_id == team_id
                ),
                Game.game_date < game_date,
                Game.game_status == 'finished'
            )
        ).order_by(desc(Game.game_date)).limit(last_n_games).all()
        
        if len(recent_games) < 5:  # Need at least 5 games
            return {
                'win_pct': 0.5,
                'point_differential': 0.0,
                'performance_factor': 1.0
            }
        
        wins = 0
        total_point_diff = 0.0
        
        for game in recent_games:
            if game.home_score is None or game.away_score is None:
                continue
            
            is_home = (game.home_team_id == team_id)
            our_score = game.home_score if is_home else game.away_score
            opp_score = game.away_score if is_home else game.home_score
            
            if our_score > opp_score:
                wins += 1
            
            point_diff = our_score - opp_score
            total_point_diff += point_diff
        
        win_pct = wins / len(recent_games)
        avg_point_diff = total_point_diff / len(recent_games)
        
        # Calculate adjustment factor
        # If team is 7-3 or better (70%+ win rate): +1-2% boost
        if win_pct >= 0.70:
            performance_factor = 1.02
        # If team is 6-4 (60% win rate): +0.5% boost
        elif win_pct >= 0.60:
            performance_factor = 1.005
        # If team is 3-7 or worse (30% or less): -1-2% penalty
        elif win_pct <= 0.30:
            performance_factor = 0.98
        # If team is 4-6 (40% win rate): -0.5% penalty
        elif win_pct <= 0.40:
            performance_factor = 0.995
        # Otherwise: neutral
        else:
            performance_factor = 1.0
        
        return {
            'win_pct': round(win_pct, 3),
            'point_differential': round(avg_point_diff, 2),
            'performance_factor': performance_factor,
            'games_analyzed': len(recent_games)
        }
    
    def calculate_game_importance(
        self,
        game_id: int,
        team_id: int
    ) -> Dict[str, any]:
        """
        Calculate game importance (playoff implications, division/conference games).
        
        Returns:
            Dict with importance level and adjustment factor
        """
        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return {'importance_factor': 1.0}
        
        # Check if it's a division game
        our_team = self.db.query(Team).filter(Team.team_id == team_id).first()
        opponent_team_id = game.away_team_id if game.home_team_id == team_id else game.home_team_id
        opponent_team = self.db.query(Team).filter(Team.team_id == opponent_team_id).first()
        
        is_division_game = False
        is_conference_game = False
        
        if our_team and opponent_team:
            is_division_game = (our_team.division == opponent_team.division and our_team.division is not None)
            is_conference_game = (our_team.conference == opponent_team.conference and our_team.conference is not None)
        
        # For now, we'll use a simplified importance calculation
        # In a full implementation, we'd check playoff standings
        # Division games are more important (4 games/year vs 2-3 for other conference teams)
        importance_factor = 1.0
        
        if is_division_game:
            importance_factor = 1.01  # Small boost for division games
        elif is_conference_game:
            importance_factor = 1.005  # Tiny boost for conference games
        
        # Calculate playoff implications
        playoff_importance = self._calculate_playoff_importance(team_id, opponent_team_id, game.game_date, game.season_id)
        
        # Combine factors
        if playoff_importance.get('is_must_win', False):
            importance_factor = max(importance_factor, 1.02)  # At least 2% boost for must-win
        elif playoff_importance.get('is_playoff_race', False):
            importance_factor = max(importance_factor, 1.015)  # 1.5% boost for playoff race games
        
        return {
            'is_division_game': is_division_game,
            'is_conference_game': is_conference_game,
            'playoff_importance': playoff_importance,
            'importance_factor': importance_factor
        }
    
    def _calculate_playoff_importance(
        self,
        team_id: int,
        opponent_team_id: int,
        game_date: date,
        season_id: int
    ) -> Dict[str, any]:
        """
        Calculate playoff race implications for a game.
        
        Returns:
            Dict with playoff race status and must-win indicator
        """
        # Calculate both teams' records
        our_record = self._calculate_team_record(team_id, game_date, season_id)
        opponent_record = self._calculate_team_record(opponent_team_id, game_date, season_id)
        
        if not our_record or not opponent_record:
            return {'is_playoff_race': False, 'is_must_win': False}
        
        our_win_pct = our_record['win_pct']
        opponent_win_pct = opponent_record['win_pct']
        
        # In NBA, typically need ~45% win rate to be in playoff contention
        # Top 8 teams in each conference make playoffs
        # If both teams are above 45% or close, it's a playoff race game
        playoff_threshold = 0.45
        
        is_playoff_race = (
            (our_win_pct >= playoff_threshold - 0.05 or opponent_win_pct >= playoff_threshold - 0.05) and
            (our_win_pct <= 0.70 and opponent_win_pct <= 0.70)  # Not elite teams (they're always in)
        )
        
        # Must-win: team is on the bubble (45-50% win rate) and opponent is also competitive
        is_must_win = (
            (0.45 <= our_win_pct <= 0.55) and
            (opponent_win_pct >= 0.40)  # Opponent is also competitive
        )
        
        return {
            'is_playoff_race': is_playoff_race,
            'is_must_win': is_must_win,
            'our_win_pct': our_win_pct,
            'opponent_win_pct': opponent_win_pct
        }
    
    def _calculate_team_record(
        self,
        team_id: int,
        before_date: date,
        season_id: int
    ) -> Optional[Dict[str, any]]:
        """
        Calculate team's win/loss record before a given date.
        
        Returns:
            Dict with wins, losses, win_pct, or None if insufficient data
        """
        games = self.db.query(Game).filter(
            and_(
                or_(
                    Game.home_team_id == team_id,
                    Game.away_team_id == team_id
                ),
                Game.season_id == season_id,
                Game.game_date < before_date,
                Game.game_status == 'finished',
                Game.home_score.isnot(None),
                Game.away_score.isnot(None)
            )
        ).all()
        
        if len(games) < 10:  # Need at least 10 games
            return None
        
        wins = 0
        losses = 0
        
        for game in games:
            is_home = (game.home_team_id == team_id)
            our_score = game.home_score if is_home else game.away_score
            opp_score = game.away_score if is_home else game.home_score
            
            if our_score > opp_score:
                wins += 1
            else:
                losses += 1
        
        total_games = wins + losses
        win_pct = wins / total_games if total_games > 0 else 0.0
        
        return {
            'wins': wins,
            'losses': losses,
            'win_pct': round(win_pct, 3),
            'games_played': total_games
        }
    
    def calculate_clutch_performance(
        self,
        player_id: int,
        season_id: Optional[int] = None,
        last_n_games: int = 20
    ) -> Dict[str, any]:
        """
        Calculate player's performance in close games vs blowouts.
        
        Returns:
            Dict with clutch stats and adjustment factor
        """
        from app.models.season import Season
        from app.models.player_game_stat import PlayerGameStat
        
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return {'clutch_factor': 1.0}
            season_id = season.season_id
        
        # Get recent games
        recent_games = self.db.query(Game).join(
            PlayerGameStat, Game.game_id == PlayerGameStat.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                Game.home_score.isnot(None),
                Game.away_score.isnot(None),
                PlayerGameStat.minutes_played > 0
            )
        ).order_by(desc(Game.game_date)).limit(last_n_games).all()
        
        if len(recent_games) < 10:
            return {'clutch_factor': 1.0}
        
        close_game_stats = []  # Games decided by ≤5 points
        blowout_game_stats = []  # Games decided by ≥15 points
        
        for game in recent_games:
            stat = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.player_id == player_id,
                    PlayerGameStat.game_id == game.game_id
                )
            ).first()
            
            if not stat:
                continue
            
            point_diff = abs(game.home_score - game.away_score)
            
            if point_diff <= 5:
                close_game_stats.append(stat)
            elif point_diff >= 15:
                blowout_game_stats.append(stat)
        
        if len(close_game_stats) < 3 or len(blowout_game_stats) < 3:
            return {'clutch_factor': 1.0}
        
        # Calculate averages
        close_avg_points = sum(s.points or 0 for s in close_game_stats) / len(close_game_stats)
        blowout_avg_points = sum(s.points or 0 for s in blowout_game_stats) / len(blowout_game_stats)
        
        # If player performs better in close games, boost for competitive matchups
        if close_avg_points > blowout_avg_points + 2:  # At least 2 points better in close games
            clutch_factor = 1.02
        elif close_avg_points > blowout_avg_points + 1:
            clutch_factor = 1.01
        elif blowout_avg_points > close_avg_points + 2:  # Better in blowouts
            clutch_factor = 0.99
        else:
            clutch_factor = 1.0
        
        return {
            'close_games': len(close_game_stats),
            'blowout_games': len(blowout_game_stats),
            'close_avg_points': round(close_avg_points, 2),
            'blowout_avg_points': round(blowout_avg_points, 2),
            'clutch_factor': clutch_factor
        }
    
    def calculate_time_of_day_factor(
        self,
        game_id: int,
        player_id: int,
        season_id: Optional[int] = None
    ) -> float:
        """
        Calculate time of day adjustment factor (day games vs night games).
        
        Returns:
            Adjustment factor (0.98 to 1.02)
        """
        from app.models.game_schedule import GameSchedule
        from app.models.player_game_stat import PlayerGameStat
        
        # Get game time from schedule
        schedule = self.db.query(GameSchedule).filter(GameSchedule.game_id == game_id).first()
        if not schedule or not schedule.game_time:
            return 1.0
        
        # Determine if it's a day game (before 6 PM local time)
        game_hour = schedule.game_time.hour
        is_day_game = game_hour < 18  # Before 6 PM
        
        if season_id is None:
            from app.models.season import Season
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return 1.0
            season_id = season.season_id
        
        # Get player's historical performance in day vs night games
        # Get all games with game times
        all_games = self.db.query(Game).join(
            GameSchedule, Game.game_id == GameSchedule.game_id
        ).filter(
            and_(
                Game.season_id == season_id,
                Game.game_status == 'finished',
                GameSchedule.game_time.isnot(None)
            )
        ).all()
        
        day_game_stats = []
        night_game_stats = []
        
        for game in all_games:
            schedule = self.db.query(GameSchedule).filter(GameSchedule.game_id == game.game_id).first()
            if not schedule or not schedule.game_time:
                continue
            
            stat = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.player_id == player_id,
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.minutes_played > 0
                )
            ).first()
            
            if not stat:
                continue
            
            if schedule.game_time.hour < 18:
                day_game_stats.append(stat.points)
            else:
                night_game_stats.append(stat.points)
        
        if len(day_game_stats) < 5 or len(night_game_stats) < 5:
            return 1.0
        
        day_avg = sum(day_game_stats) / len(day_game_stats)
        night_avg = sum(night_game_stats) / len(night_game_stats)
        
        # If player performs significantly better in day/night games, apply adjustment
        if is_day_game:
            if day_avg > night_avg + 2:  # At least 2 points better in day games
                return 1.02
            elif day_avg < night_avg - 2:  # Worse in day games
                return 0.98
        else:  # Night game
            if night_avg > day_avg + 2:  # Better in night games
                return 1.02
            elif night_avg < day_avg - 2:  # Worse in night games
                return 0.98
        
        return 1.0
    
    def calculate_national_tv_factor(
        self,
        game_id: int
    ) -> float:
        """
        Calculate national TV game adjustment factor.
        
        National TV games are typically:
        - Prime time (7 PM - 10 PM ET)
        - Weekend games
        - High-profile matchups
        
        Returns:
            Adjustment factor (1.0 to 1.02)
        """
        from app.models.game_schedule import GameSchedule
        
        schedule = self.db.query(GameSchedule).filter(GameSchedule.game_id == game_id).first()
        if not schedule or not schedule.game_time:
            return 1.0
        
        # Check if it's prime time (7 PM - 10 PM ET)
        # Note: This is simplified - would need timezone conversion for accuracy
        game_hour = schedule.game_time.hour
        is_prime_time = 19 <= game_hour <= 22  # 7 PM - 10 PM
        
        # Check if it's a weekend
        game_weekday = schedule.game_time.weekday()  # 0 = Monday, 6 = Sunday
        is_weekend = game_weekday >= 5  # Saturday or Sunday
        
        # National TV games are typically prime time or weekend
        if is_prime_time or is_weekend:
            return 1.01  # Small boost for national TV exposure
        
        return 1.0
    
    def get_game_context(
        self,
        game_id: int,
        team_id: int
    ) -> Dict[str, any]:
        """
        Get full game context for a team.
        
        Returns:
            Dict with all context factors
        """
        cache_key = (game_id, team_id)
        if cache_key in self._context_cache:
            return self._context_cache[cache_key]

        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            return {}
        
        rest_days = self.calculate_rest_days(team_id, game.game_date)
        rest_days_factor = self.calculate_rest_days_factor(rest_days)
        relative_rest_factor = self.calculate_relative_rest_advantage(game_id, team_id)
        team_performance = self.calculate_team_recent_performance(team_id, game.game_date)
        game_importance = self.calculate_game_importance(game_id, team_id)
        national_tv_factor = self.calculate_national_tv_factor(game_id)
        travel = self.calculate_travel_impact(team_id, game_id)
        blowout = self.calculate_blowout_risk(game_id)
        
        context = {
            'rest_days': rest_days,
            'rest_days_factor': rest_days_factor,
            'relative_rest_factor': relative_rest_factor,
            'team_performance': team_performance,
            'game_importance': game_importance,
            'national_tv_factor': national_tv_factor,
            'travel': travel,
            'blowout': blowout,
            'is_home': (game.home_team_id == team_id)
        }
        self._context_cache[cache_key] = context
        return context

