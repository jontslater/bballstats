"""
PlayerTeamMatchup model - Historical player performance against specific teams
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PlayerTeamMatchup(Base):
    __tablename__ = "player_team_matchups"

    id = Column(Integer, primary_key=True, index=True)
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL'
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    opponent_team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.season_id"), nullable=False)
    
    # Aggregated stats
    games_played = Column(Integer)
    avg_points = Column(Float)
    avg_rebounds = Column(Float)
    avg_assists = Column(Float)
    avg_minutes = Column(Float)
    last_5_games_avg_points = Column(Float)
    best_game_points = Column(Integer)
    worst_game_points = Column(Integer)
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    player = relationship("Player", back_populates="matchups")
    opponent_team = relationship("Team", foreign_keys=[opponent_team_id])

    # Unique constraint - one record per player/team/season per sport
    __table_args__ = (UniqueConstraint('sport', 'player_id', 'opponent_team_id', 'season_id', name='_sport_player_team_season_uc'),)

    def __repr__(self):
        return f"<PlayerTeamMatchup {self.player_id} vs {self.opponent_team_id}: {self.avg_points} PPG>"





