"""
BettingLine model - Actual betting lines from sportsbooks
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BettingLine(Base):
    __tablename__ = "betting_lines"

    line_id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    stat_type = Column(String(20), nullable=False)  # points, rebounds, assists
    
    # Betting line data
    over_line = Column(Float, nullable=True)  # e.g., 24.5
    under_line = Column(Float, nullable=True)  # Usually same as over_line
    over_odds = Column(String(20), nullable=True)  # e.g., "-110", "+150"
    under_odds = Column(String(20), nullable=True)
    
    # Source
    sportsbook = Column(String(50), nullable=True)  # e.g., "DraftKings", "FanDuel"
    source = Column(String(50), default="manual")  # "manual", "api", "scraped"
    
    # Value analysis
    our_prediction = Column(Float, nullable=True)  # Our predicted line
    our_probability = Column(Float, nullable=True)  # Our probability
    value_score = Column(Float, nullable=True)  # Positive = good value, negative = bad value
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    game = relationship("Game")
    player = relationship("Player")

    # Unique constraint - one line per player/stat/game/sportsbook
    __table_args__ = (UniqueConstraint('game_id', 'player_id', 'stat_type', 'sportsbook', name='_game_player_stat_sportsbook_uc'),)

    def __repr__(self):
        return f"<BettingLine {self.player_id} {self.stat_type} Over {self.over_line} ({self.sportsbook})>"


