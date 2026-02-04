"""
InjuryImpactHistory model - Historical patterns of how injuries affect minutes/usage
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Float, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class InjuryImpactHistory(Base):
    __tablename__ = "injury_impact_history"

    id = Column(Integer, primary_key=True, index=True)
    injured_player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    beneficiary_player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    
    # Impact metrics
    minutes_increase = Column(Integer)  # how many more minutes beneficiary got
    stat_increase_points = Column(Float)
    stat_increase_rebounds = Column(Float)
    stat_increase_assists = Column(Float)
    position = Column(String(10))  # position of injured player
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    injured_player = relationship("Player", foreign_keys=[injured_player_id])
    beneficiary_player = relationship("Player", foreign_keys=[beneficiary_player_id])
    game = relationship("Game")

    def __repr__(self):
        return f"<InjuryImpactHistory {self.beneficiary_player_id} got +{self.minutes_increase} min when {self.injured_player_id} was out>"





