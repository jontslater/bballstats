"""
Lineup model - Confirmed starting lineups
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Lineup(Base):
    __tablename__ = "lineups"

    lineup_id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    position = Column(String(10))  # PG, SG, SF, PF, C
    is_starter = Column(Boolean, default=True)
    confirmed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    game = relationship("Game", back_populates="lineups")
    team = relationship("Team", foreign_keys=[team_id])
    player = relationship("Player")

    def __repr__(self):
        return f"<Lineup {self.player_id} ({'starter' if self.is_starter else 'bench'}) in game {self.game_id}>"





