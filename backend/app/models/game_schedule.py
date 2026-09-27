"""
GameSchedule model - Upcoming games
"""
from sqlalchemy import Column, Integer, ForeignKey, Date, DateTime, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class GameSchedule(Base):
    __tablename__ = "game_schedules"

    schedule_id = Column(Integer, primary_key=True, index=True)
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL'
    game_date = Column(Date, nullable=False, index=True)
    home_team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    game_time = Column(DateTime(timezone=True))
    season_id = Column(Integer, ForeignKey("seasons.season_id"), nullable=False)
    status = Column(String(20), default="scheduled")  # scheduled, postponed, cancelled
    nba_game_id = Column(String(20), nullable=True, index=True)  # DEPRECATED: Use external_game_id instead
    external_game_id = Column(String(50), nullable=True, index=True)  # Sport-agnostic external game ID (ESPN, NBA.com, etc.)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=True)  # link to actual game when played
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
    season = relationship("Season")
    game = relationship("Game", back_populates="schedules")

    def __repr__(self):
        return f"<GameSchedule {self.away_team_id} @ {self.home_team_id} on {self.game_date}>"

