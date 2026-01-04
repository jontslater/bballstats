"""
Player model - NBA players
"""
from sqlalchemy import Column, Integer, String, Date, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Player(Base):
    __tablename__ = "players"

    player_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    position = Column(String(10))  # PG, SG, SF, PF, C
    height = Column(Integer)  # inches
    weight = Column(Integer)  # pounds
    birth_date = Column(Date)
    current_team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    team = relationship("Team", back_populates="players")
    game_stats = relationship("PlayerGameStat", back_populates="player")
    injuries = relationship("Injury", back_populates="player")
    matchups = relationship("PlayerTeamMatchup", back_populates="player")
    predictions = relationship("Prediction", back_populates="player")
    plays = relationship("UserPlay", back_populates="player")

    def __repr__(self):
        return f"<Player {self.name} ({self.position})>"


