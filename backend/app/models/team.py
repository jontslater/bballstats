"""
Team model - NBA and NFL teams
"""
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Team(Base):
    __tablename__ = "teams"

    team_id = Column(Integer, primary_key=True, index=True)
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL'
    name = Column(String, nullable=False)  # "Los Angeles Lakers" or "Kansas City Chiefs"
    abbreviation = Column(String(10), nullable=False)  # "LAL" or "KC"
    conference = Column(String(10))  # "West" or "East" (NBA) or "AFC" or "NFC" (NFL)
    division = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Unique constraint: abbreviation must be unique per sport
    __table_args__ = (UniqueConstraint('sport', 'abbreviation', name='_sport_abbreviation_uc'),)

    # Relationships
    home_games = relationship("Game", foreign_keys="Game.home_team_id", back_populates="home_team")
    away_games = relationship("Game", foreign_keys="Game.away_team_id", back_populates="away_team")
    players = relationship("Player", back_populates="team")

    def __repr__(self):
        return f"<Team {self.abbreviation}: {self.name}>"





