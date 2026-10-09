"""
Pace Calculator

Calculates team and game pace (possessions per game).
"""
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session
from typing import Optional, Dict, Tuple
from app.models.game import Game
from app.models.player_game_stat import PlayerGameStat
from app.models.team import Team
from app.models.season import Season


class PaceCalculator:
    """Calculate team and game pace."""

    def __init__(self, db: Session):
        self.db = db
        # Per-run memoization: calculate_team_pace used to scan every team
        # game (and every player-stat row in those games) on each call.
        self._team_pace_cache: Dict[Tuple[int, int], Optional[float]] = {}
        self._recent_pace_cache: Dict[Tuple[int, int, int], Optional[float]] = {}
        self._game_pace_cache: Dict[int, Optional[float]] = {}

    def calculate_team_pace(
        self,
        team_id: int,
        season_id: Optional[int] = None
    ) -> Optional[float]:
        """
        Calculate average pace for a team.

        Pace = (FGA + 0.44 * FTA + TO) / 2
        This is a simplified formula - actual NBA pace uses play-by-play data.

        Args:
            team_id: Team to analyze
            season_id: Season to analyze (default: current)

        Returns:
            Average pace (possessions per game) or None if insufficient data
        """
        if season_id is None:
            season = self.db.query(Season).filter(
                Season.is_current == True
            ).first()
            if not season:
                raise ValueError("No current season found.")
            season_id = season.season_id

        cache_key = (team_id, season_id)
        if cache_key in self._team_pace_cache:
            return self._team_pace_cache[cache_key]

        # One grouped query instead of: all team games + per-game player stats.
        # Same formula and skip-empty-game behavior as the original loop.
        game_totals = self.db.query(
            PlayerGameStat.game_id,
            func.sum(func.coalesce(PlayerGameStat.field_goals_attempted, 0)).label('fga'),
            func.sum(func.coalesce(PlayerGameStat.free_throws_attempted, 0)).label('fta'),
            func.sum(func.coalesce(PlayerGameStat.turnovers, 0)).label('turnovers'),
        ).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.team_id == team_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
            )
        ).group_by(PlayerGameStat.game_id).all()

        if not game_totals:
            self._team_pace_cache[cache_key] = None
            return None

        total_pace = 0.0
        games_counted = 0
        for _game_id, fga, fta, turnovers in game_totals:
            possessions = ((fga or 0) + 0.44 * (fta or 0) + (turnovers or 0)) / 2
            total_pace += possessions
            games_counted += 1

        if games_counted == 0:
            self._team_pace_cache[cache_key] = None
            return None

        result = round(total_pace / games_counted, 2)
        self._team_pace_cache[cache_key] = result
        return result

    def calculate_recent_team_pace(
        self,
        team_id: int,
        season_id: Optional[int] = None,
        last_n_games: int = 10
    ) -> Optional[float]:
        """
        Calculate team's pace in recent games (last N games).

        Returns:
            Average pace in last N games, or None if insufficient data
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                return None
            season_id = season.season_id

        cache_key = (team_id, season_id, last_n_games)
        if cache_key in self._recent_pace_cache:
            return self._recent_pace_cache[cache_key]

        from sqlalchemy import desc

        recent_games = self.db.query(Game).filter(
            and_(
                or_(
                    Game.home_team_id == team_id,
                    Game.away_team_id == team_id
                ),
                Game.season_id == season_id,
                Game.game_status == 'finished',
                Game.game_date.isnot(None)
            )
        ).order_by(desc(Game.game_date)).limit(last_n_games).all()

        if len(recent_games) < 5:  # Need at least 5 games
            self._recent_pace_cache[cache_key] = None
            return None

        paces = []
        for game in recent_games:
            game_pace = self.calculate_game_pace(game.game_id)
            if game_pace:
                paces.append(game_pace)

        if len(paces) < 3:  # Need at least 3 games with pace data
            self._recent_pace_cache[cache_key] = None
            return None

        result = round(sum(paces) / len(paces), 2)
        self._recent_pace_cache[cache_key] = result
        return result

    def calculate_game_pace(self, game_id: int) -> Optional[float]:
        """
        Calculate pace for a specific game.

        Returns:
            Game pace (possessions) or None
        """
        if game_id in self._game_pace_cache:
            return self._game_pace_cache[game_id]

        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        if not game or game.game_status != 'finished':
            self._game_pace_cache[game_id] = None
            return None

        rows = self.db.query(
            PlayerGameStat.team_id,
            func.sum(func.coalesce(PlayerGameStat.field_goals_attempted, 0)),
            func.sum(func.coalesce(PlayerGameStat.free_throws_attempted, 0)),
            func.sum(func.coalesce(PlayerGameStat.turnovers, 0)),
        ).filter(
            PlayerGameStat.game_id == game_id,
            PlayerGameStat.team_id.in_([game.home_team_id, game.away_team_id]),
        ).group_by(PlayerGameStat.team_id).all()

        by_team = {team_id: (fga or 0, fta or 0, to or 0) for team_id, fga, fta, to in rows}
        if game.home_team_id not in by_team or game.away_team_id not in by_team:
            self._game_pace_cache[game_id] = None
            return None

        home_fga, home_fta, home_to = by_team[game.home_team_id]
        away_fga, away_fta, away_to = by_team[game.away_team_id]
        home_possessions = (home_fga + 0.44 * home_fta + home_to) / 2
        away_possessions = (away_fga + 0.44 * away_fta + away_to) / 2
        result = round((home_possessions + away_possessions) / 2, 2)
        self._game_pace_cache[game_id] = result
        return result

    def calculate_all_team_paces(self, season_id: Optional[int] = None) -> Dict[int, float]:
        """
        Calculate pace for all teams.

        Returns:
            Dict mapping team_id to pace
        """
        teams = self.db.query(Team).all()
        paces = {}

        for team in teams:
            pace = self.calculate_team_pace(team.team_id, season_id)
            if pace:
                paces[team.team_id] = pace

        return paces
