"""
Team Position Defense Calculator

Calculates how teams perform defensively against different positions.
"""
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session
from datetime import date, timedelta
from typing import Optional, List, Dict
from app.models.team_position_defense import TeamPositionDefense
from app.models.player_game_stat import PlayerGameStat
from app.models.player import Player
from app.models.game import Game
from app.models.team import Team
from app.models.season import Season


class TeamDefenseCalculator:
    """Calculate team defensive stats by position."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def calculate_all_teams_positions(self, season_id: Optional[int] = None) -> Dict[str, int]:
        """
        Calculate defense stats for all teams and all positions.
        
        Returns:
            Dict with counts of records created/updated
        """
        # Get season if not provided (use current season)
        if season_id is None:
            season = self.db.query(Season).filter(
                Season.is_current == True
            ).first()
            if not season:
                raise ValueError("No current season found. Please specify season_id.")
            season_id = season.season_id
        
        # Get all teams
        teams = self.db.query(Team).all()
        positions = ['PG', 'SG', 'SF', 'PF', 'C']
        
        created = 0
        updated = 0
        
        for team in teams:
            for position in positions:
                result = self.calculate_team_position_defense(
                    team_id=team.team_id,
                    position=position,
                    season_id=season_id
                )
                if result:
                    created += 1
                else:
                    updated += 1
        
        return {"created": created, "updated": updated}
    
    def calculate_team_position_defense(
        self,
        team_id: int,
        position: str,
        season_id: int,
        min_games: int = 3
    ) -> Optional[TeamPositionDefense]:
        """
        Calculate defensive stats for a specific team against a specific position.
        
        Args:
            team_id: Team to analyze
            position: Position (PG, SG, SF, PF, C)
            season_id: Season to analyze
            min_games: Minimum games required to calculate stats
        
        Returns:
            TeamPositionDefense object if enough data, None otherwise
        """
        # Get all games in this season where this team played
        season = self.db.query(Season).filter(Season.season_id == season_id).first()
        if not season:
            return None
        
        # Get games where this team was the opponent
        # We want stats of players who played AGAINST this team
        opponent_stats = self.db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).join(
            Player, PlayerGameStat.player_id == Player.player_id
        ).filter(
            and_(
                PlayerGameStat.opponent_team_id == team_id,
                Game.game_date >= season.start_date,
                Game.game_date <= season.end_date,
                Game.game_status == 'finished',
                Player.position == position,
                PlayerGameStat.minutes_played > 0  # Only players who actually played
            )
        ).all()
        
        if len(opponent_stats) < min_games:
            # Not enough data
            return None
        
        # Calculate overall averages
        total_games = len(set(stat.game_id for stat in opponent_stats))
        avg_points = sum(stat.points or 0 for stat in opponent_stats) / len(opponent_stats)
        avg_rebounds = sum(stat.rebounds or 0 for stat in opponent_stats) / len(opponent_stats)
        avg_assists = sum(stat.assists or 0 for stat in opponent_stats) / len(opponent_stats)
        avg_minutes = sum(stat.minutes_played or 0 for stat in opponent_stats) / len(opponent_stats)
        
        # Calculate home/away splits
        home_stats = [s for s in opponent_stats if not s.is_home]  # Team is away, opponent is home
        away_stats = [s for s in opponent_stats if s.is_home]  # Team is home, opponent is away
        
        home_avg_points = sum(s.points or 0 for s in home_stats) / len(home_stats) if home_stats else None
        away_avg_points = sum(s.points or 0 for s in away_stats) / len(away_stats) if away_stats else None
        
        # Calculate recent form (last 5 and 10 games)
        # Get games sorted by date
        game_ids = list(set(stat.game_id for stat in opponent_stats))
        games = self.db.query(Game).filter(Game.game_id.in_(game_ids)).order_by(
            Game.game_date.desc()
        ).all()
        
        last_5_games = games[:5] if len(games) >= 5 else games
        last_10_games = games[:10] if len(games) >= 10 else games
        
        last_5_game_ids = [g.game_id for g in last_5_games]
        last_10_game_ids = [g.game_id for g in last_10_games]
        
        last_5_stats = [s for s in opponent_stats if s.game_id in last_5_game_ids]
        last_10_stats = [s for s in opponent_stats if s.game_id in last_10_game_ids]
        
        last_5_avg_points = sum(s.points or 0 for s in last_5_stats) / len(last_5_stats) if last_5_stats else None
        last_10_avg_points = sum(s.points or 0 for s in last_10_stats) / len(last_10_stats) if last_10_stats else None
        
        # Calculate team pace (average possessions per game)
        # For now, we'll use a simple estimate: pace = (FGA + 0.44 * FTA + TO) / 2
        # This is a simplified version - we can improve later
        team_games = self.db.query(Game).filter(
            and_(
                or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
                Game.game_date >= season.start_date,
                Game.game_date <= season.end_date,
                Game.game_status == 'finished'
            )
        ).all()
        
        # Calculate average pace for this team
        # For now, set to None - we'll implement proper pace calculation later
        pace = None
        
        # Calculate defensive ranking
        # Get all teams' avg_points_allowed for this position
        all_team_stats = self.db.query(
            TeamPositionDefense.team_id,
            TeamPositionDefense.avg_points_allowed
        ).filter(
            and_(
                TeamPositionDefense.position == position,
                TeamPositionDefense.season_id == season_id,
                TeamPositionDefense.avg_points_allowed.isnot(None)
            )
        ).all()
        
        # Sort by avg_points_allowed (highest = worst defense = rank 1)
        sorted_teams = sorted(all_team_stats, key=lambda x: x[1] or 0, reverse=True)
        ranking = None
        for idx, (tid, _) in enumerate(sorted_teams, 1):
            if tid == team_id:
                ranking = idx
                break
        
        # If not found in existing rankings, calculate it
        if ranking is None:
            # Get all teams' stats for this position
            all_opponent_stats = {}
            for tid in [t.team_id for t in self.db.query(Team).all()]:
                tid_stats = self.db.query(PlayerGameStat).join(
                    Game, PlayerGameStat.game_id == Game.game_id
                ).join(
                    Player, PlayerGameStat.player_id == Player.player_id
                ).filter(
                    and_(
                        PlayerGameStat.opponent_team_id == tid,
                        Game.game_date >= season.start_date,
                        Game.game_date <= season.end_date,
                        Game.game_status == 'finished',
                        Player.position == position,
                        PlayerGameStat.minutes_played > 0
                    )
                ).all()
                
                if tid_stats:
                    all_opponent_stats[tid] = sum(s.points or 0 for s in tid_stats) / len(tid_stats)
            
            # Calculate ranking
            sorted_avg_points = sorted(all_opponent_stats.values(), reverse=True)
            if team_id in all_opponent_stats:
                ranking = sorted_avg_points.index(all_opponent_stats[team_id]) + 1
        
        # Get or create TeamPositionDefense record
        defense = self.db.query(TeamPositionDefense).filter(
            and_(
                TeamPositionDefense.team_id == team_id,
                TeamPositionDefense.position == position,
                TeamPositionDefense.season_id == season_id
            )
        ).first()
        
        is_new = defense is None
        if is_new:
            defense = TeamPositionDefense(
                team_id=team_id,
                position=position,
                season_id=season_id
            )
        
        # Update stats
        defense.games_analyzed = total_games
        defense.avg_points_allowed = round(avg_points, 2)
        defense.avg_rebounds_allowed = round(avg_rebounds, 2)
        defense.avg_assists_allowed = round(avg_assists, 2)
        defense.avg_minutes_allowed = round(avg_minutes, 2)
        defense.defensive_ranking = ranking
        defense.home_avg_points_allowed = round(home_avg_points, 2) if home_avg_points else None
        defense.away_avg_points_allowed = round(away_avg_points, 2) if away_avg_points else None
        defense.last_5_games_avg_points_allowed = round(last_5_avg_points, 2) if last_5_avg_points else None
        defense.last_10_games_avg_points_allowed = round(last_10_avg_points, 2) if last_10_avg_points else None
        defense.pace = pace
        
        if is_new:
            self.db.add(defense)
        
        self.db.commit()
        self.db.refresh(defense)
        
        return defense

