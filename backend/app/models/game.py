"""
Game model - NBA and NFL games
"""
from sqlalchemy import Column, Integer, Date, ForeignKey, String, Float, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Game(Base):
    __tablename__ = "games"

    game_id = Column(Integer, primary_key=True, index=True)
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL' (inherited from season)
    game_date = Column(Date, nullable=False, index=True)
    season_id = Column(Integer, ForeignKey("seasons.season_id"), nullable=False)
    home_team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    game_status = Column(String(20), default="scheduled")  # scheduled, in_progress, finished
    pace = Column(Float, nullable=True)  # possessions per game (NBA) or plays per game (NFL)
    espn_game_id = Column(String(20), nullable=True, index=True)  # ESPN game ID (not unique across sports)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    season = relationship("Season")
    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_games")
    away_team = relationship("Team", foreign_keys=[away_team_id], back_populates="away_games")
    player_stats = relationship("PlayerGameStat", back_populates="game")
    predictions = relationship("Prediction", back_populates="game")
    schedules = relationship("GameSchedule", back_populates="game")
    lineups = relationship("Lineup", back_populates="game")

    def __repr__(self):
        return f"<Game {self.away_team_id} @ {self.home_team_id} on {self.game_date}>"

