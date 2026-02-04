"""
TeamPositionDefense model - Aggregated team defensive stats by position
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Float, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class TeamPositionDefense(Base):
    __tablename__ = "team_position_defense"

    id = Column(Integer, primary_key=True, index=True)
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL'
    team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    position = Column(String(10), nullable=False)  # PG, SG, SF, PF, C (NBA) or QB, RB, WR, TE (NFL)
    season_id = Column(Integer, ForeignKey("seasons.season_id"), nullable=False)
    
    # Aggregated stats
    games_analyzed = Column(Integer)
    avg_points_allowed = Column(Float)
    avg_rebounds_allowed = Column(Float)
    avg_assists_allowed = Column(Float)
    avg_minutes_allowed = Column(Float)
    defensive_ranking = Column(Integer)  # 1-30, 1 = worst defense
    
    # Splits
    home_avg_points_allowed = Column(Float)
    away_avg_points_allowed = Column(Float)
    last_5_games_avg_points_allowed = Column(Float)
    last_10_games_avg_points_allowed = Column(Float)
    
    # Pace
    pace = Column(Float)  # team's average pace
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Unique constraint - one record per team/position/season per sport
    __table_args__ = (UniqueConstraint('sport', 'team_id', 'position', 'season_id', name='_sport_team_pos_season_uc'),)

    def __repr__(self):
        return f"<TeamPositionDefense {self.team_id} vs {self.position}: Rank {self.defensive_ranking}>"





