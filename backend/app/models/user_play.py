"""
UserPlay model - User-created betting plays (NBA and NFL)
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Float, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class UserPlay(Base):
    __tablename__ = "user_plays"

    play_id = Column(Integer, primary_key=True, index=True)
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL'
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    stat_type = Column(String(30), nullable=False)  # points, rebounds, assists (NBA) or passing_yards, etc. (NFL)
    
    # Bet details
    bet_line = Column(String(50))  # e.g., "Over 24.5", "Under 10.5"
    
    # Prediction data (from prediction)
    predicted_min = Column(Integer)
    predicted_max = Column(Integer)
    likelihood_score = Column(Float)
    
    # User notes
    notes = Column(Text)
    
    # Status tracking
    status = Column(String(20), default="pending")  # pending, hit, miss
    actual_result = Column(Integer, nullable=True)  # filled in after game
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    player = relationship("Player", back_populates="plays")
    game = relationship("Game")
    parlays = relationship("Parlay", secondary="parlay_plays", back_populates="plays")

    def __repr__(self):
        return f"<UserPlay {self.player_id} {self.stat_type} {self.bet_line} - {self.status}>"

