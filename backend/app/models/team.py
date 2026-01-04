"""
Team model - NBA teams
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Team(Base):
    __tablename__ = "teams"

    team_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # "Los Angeles Lakers"
    abbreviation = Column(String(10), nullable=False, unique=True)  # "LAL"
    conference = Column(String(10))  # "West" or "East"
    division = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    home_games = relationship("Game", foreign_keys="Game.home_team_id", back_populates="home_team")
    away_games = relationship("Game", foreign_keys="Game.away_team_id", back_populates="away_team")
    players = relationship("Player", back_populates="team")

    def __repr__(self):
        return f"<Team {self.abbreviation}: {self.name}>"


