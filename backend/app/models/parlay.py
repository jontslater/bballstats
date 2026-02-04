"""
Parlay model - User-created parlay bets combining multiple plays
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Float, Text, DateTime, Boolean, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# Association table for parlay plays
parlay_plays = Table(
    'parlay_plays',
    Base.metadata,
    Column('parlay_id', Integer, ForeignKey('parlays.parlay_id'), primary_key=True),
    Column('play_id', Integer, ForeignKey('user_plays.play_id'), primary_key=True)
)


class Parlay(Base):
    __tablename__ = "parlays"

    parlay_id = Column(Integer, primary_key=True, index=True)
    
    # Sport
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL'
    
    # Parlay details
    name = Column(String(200), nullable=True)  # Optional name for the parlay
    total_odds = Column(Float, nullable=True)  # Combined odds (e.g., +500)
    total_probability = Column(Float, nullable=True)  # Combined probability (0.0-1.0)
    
    # Status tracking
    status = Column(String(20), default="pending")  # pending, hit, miss, partial
    legs_hit = Column(Integer, default=0)  # Number of legs that hit
    total_legs = Column(Integer, nullable=False)  # Total number of legs
    
    # User notes
    notes = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    plays = relationship("UserPlay", secondary=parlay_plays, back_populates="parlays")

    def __repr__(self):
        return f"<Parlay {self.parlay_id} - {self.total_legs} legs - {self.status}>"





