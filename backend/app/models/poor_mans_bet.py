"""
Poor Man's Bet Challenge models (NBA and NFL).
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Float, Text, Date, DateTime, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PoorMansBetChallenge(Base):
    """Poor Man's Bet Challenge - tracks the overall challenge."""
    __tablename__ = "poor_mans_bet_challenges"

    challenge_id = Column(Integer, primary_key=True, index=True)
    
    # Sport
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL'
    
    # Challenge details
    name = Column(String(200), nullable=True)
    start_amount = Column(DECIMAL(10, 2), nullable=False)  # $1-$5
    target_amount = Column(DECIMAL(10, 2), nullable=False)  # ~$1000
    days_target = Column(Integer, nullable=False)  # 14 days default
    current_bankroll = Column(DECIMAL(10, 2), nullable=False)  # Current amount
    status = Column(String(20), default='active')  # active, completed, failed
    
    # Dates
    start_date = Column(Date, nullable=False)
    target_date = Column(Date, nullable=True)  # start_date + days_target
    
    # Progress tracking
    current_day = Column(Integer, default=1)  # Which day of the challenge
    total_bets = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    days = relationship("PoorMansBetDay", back_populates="challenge", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<PoorMansBetChallenge {self.challenge_id}: ${self.current_bankroll:.2f} / ${self.target_amount:.2f}>"


class PoorMansBetDay(Base):
    """Poor Man's Bet Day - tracks each day's bet in the challenge."""
    __tablename__ = "poor_mans_bet_days"

    day_id = Column(Integer, primary_key=True, index=True)
    challenge_id = Column(Integer, ForeignKey("poor_mans_bet_challenges.challenge_id"), nullable=False)
    
    # Day details
    day_number = Column(Integer, nullable=False)  # Day 1, 2, 3, etc.
    bet_date = Column(Date, nullable=False)
    
    # Bankroll tracking
    starting_bankroll = Column(DECIMAL(10, 2), nullable=False)
    bet_amount = Column(DECIMAL(10, 2), nullable=False)
    target_return = Column(DECIMAL(10, 2), nullable=True)  # Expected return if wins
    actual_return = Column(DECIMAL(10, 2), nullable=True)  # Actual return after bet resolves
    ending_bankroll = Column(DECIMAL(10, 2), nullable=True)  # Bankroll after this bet
    
    # Bet details
    bet_type = Column(String(20), nullable=True)  # 'single', 'parlay'
    parlay_id = Column(Integer, ForeignKey("parlays.parlay_id"), nullable=True)  # If parlay bet
    play_id = Column(Integer, ForeignKey("user_plays.play_id"), nullable=True)  # If single bet
    
    # Status
    status = Column(String(20), default='pending')  # pending, hit, miss
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    challenge = relationship("PoorMansBetChallenge", back_populates="days")
    parlay = relationship("Parlay", foreign_keys=[parlay_id])
    play = relationship("UserPlay", foreign_keys=[play_id])
    
    def __repr__(self):
        return f"<PoorMansBetDay {self.day_id}: Day {self.day_number} - ${self.bet_amount:.2f} - {self.status}>"




