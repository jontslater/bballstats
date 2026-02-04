"""
Prediction model - Distribution-based predictions for player performance (NBA and NFL)
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Float, Text, Boolean, DateTime, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    prediction_id = Column(Integer, primary_key=True, index=True)
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL'
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    stat_type = Column(String(30), nullable=False)  # points, rebounds, assists (NBA) or passing_yards, rushing_yards, etc. (NFL)
    
    # Distribution parameters
    distribution_mean = Column(Float)  # adjusted mean (μ)
    distribution_std_dev = Column(Float)  # adjusted standard deviation (σ)
    
    # Percentiles
    percentile_10 = Column(Float)
    percentile_20 = Column(Float)
    percentile_25 = Column(Float)  # Safe bet line
    percentile_50 = Column(Float)  # Median/Standard bet line
    percentile_75 = Column(Float)
    percentile_80 = Column(Float)
    percentile_85 = Column(Float)  # Long shot line
    percentile_90 = Column(Float)
    
    # Sample size
    sample_size = Column(Integer)  # number of historical games used
    
    # Bet lines and probabilities
    safe_line = Column(Float)
    safe_probability = Column(Float)
    safe_under_probability = Column(Float)  # Probability of going UNDER the safe line
    standard_line = Column(Float)
    standard_probability = Column(Float)
    standard_under_probability = Column(Float)  # Probability of going UNDER the standard line
    long_shot_line = Column(Float)
    long_shot_probability = Column(Float)
    long_shot_under_probability = Column(Float)  # Probability of going UNDER the long shot line
    
    # Classification
    bet_type = Column(String(20))  # safe, standard, long_shot, pass
    pass_reason = Column(Text)  # if bet_type is "pass", why
    confidence_level = Column(String(10))  # HIGH, MEDIUM, LOW
    volatility_level = Column(String(10))  # LOW, MEDIUM, HIGH
    
    # Reasoning
    reasoning = Column(Text)  # key factors
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Actual results (filled after game)
    actual_result = Column(Integer, nullable=True)
    hit_safe = Column(Boolean, nullable=True)
    hit_standard = Column(Boolean, nullable=True)
    hit_long_shot = Column(Boolean, nullable=True)

    # Relationships
    player = relationship("Player", back_populates="predictions")
    game = relationship("Game", back_populates="predictions")

    def __repr__(self):
        return f"<Prediction {self.player_id} {self.stat_type}: {self.distribution_mean:.1f}±{self.distribution_std_dev:.1f} ({self.bet_type})>"


class ValueLadder(Base):
    """Value ladder recommendations stored in database."""
    __tablename__ = "value_ladders"

    ladder_id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    sport = Column(String(10), nullable=False, default='NBA')
    stat_type = Column(String(20), nullable=False)  # 'points', 'rebounds', etc.
    normal_performance = Column(Float, nullable=False)  # Historical average
    exceptional_performance = Column(Float, nullable=False)  # Predicted high
    midpoint_performance = Column(Float, nullable=False)  # Middle point
    confidence_normal = Column(Float, nullable=False)  # Confidence for normal
    confidence_midpoint = Column(Float, nullable=False)  # Confidence for midpoint
    confidence_exceptional = Column(Float, nullable=False)  # Confidence for exceptional
    expected_value_total = Column(Float, nullable=False)  # Total EV for ladder
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    player = relationship("Player")
    game = relationship("Game")

    def __repr__(self):
        return f"<ValueLadder {self.player_id} {self.stat_type}: {self.normal_performance}→{self.exceptional_performance}>"


class HistoricalSuggestedBet(Base):
    """Tracks historical suggested bets for performance analysis."""
    __tablename__ = "historical_suggested_bets"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    player_name = Column(String(100), nullable=False)
    player_team = Column(String(10), nullable=False)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    game_date = Column(Date, nullable=False)
    stat_type = Column(String(20), nullable=False)
    bet_type = Column(String(20), nullable=False)
    line = Column(Float, nullable=False)
    probability = Column(Float, nullable=False)
    confidence_level = Column(String(20), nullable=False)
    volatility_level = Column(String(20), nullable=False)
    reasoning = Column(Text, nullable=True)
    actual_result = Column(Float, nullable=True)  # Actual stat value achieved
    hit = Column(Boolean, nullable=True)  # Whether the bet hit (True/False/None for pending)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    player = relationship("Player")
    game = relationship("Game")

    def __repr__(self):
        return f"<HistoricalSuggestedBet {self.player_name} {self.stat_type} {self.line}: {'HIT' if self.hit else 'MISS' if self.hit is False else 'PENDING'}>"


class HistoricalParlay(Base):
    """Tracks historical parlays for performance analysis."""
    __tablename__ = "historical_parlays"

    id = Column(Integer, primary_key=True, index=True)
    parlay_type = Column(String(50), nullable=False)  # 'suggested', 'safe_long', 'builder', 'hot_matchup'
    num_legs = Column(Integer, nullable=False)
    combined_probability = Column(Float, nullable=False)
    odds_display = Column(String(20), nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    all_legs_hit = Column(Boolean, nullable=True)  # Whether entire parlay hit
    legs_hit_count = Column(Integer, nullable=True)  # How many legs hit
    payout_amount = Column(Float, nullable=True)  # Calculated payout if won

    def __repr__(self):
        return f"<HistoricalParlay {self.parlay_type} {self.num_legs} legs: {'WON' if self.all_legs_hit else 'LOST' if self.all_legs_hit is False else 'PENDING'}>"


class HistoricalParlayLeg(Base):
    """Individual legs of historical parlays."""
    __tablename__ = "historical_parlay_legs"

    id = Column(Integer, primary_key=True, index=True)
    parlay_id = Column(Integer, ForeignKey("historical_parlays.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    player_name = Column(String(100), nullable=False)
    player_team = Column(String(10), nullable=False)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    stat_type = Column(String(20), nullable=False)
    bet_type = Column(String(20), nullable=False)
    line = Column(Float, nullable=False)
    probability = Column(Float, nullable=False)
    actual_result = Column(Float, nullable=True)
    hit = Column(Boolean, nullable=True)

    # Relationships
    parlay = relationship("HistoricalParlay", back_populates="legs")
    player = relationship("Player")
    game = relationship("Game")

    def __repr__(self):
        return f"<HistoricalParlayLeg {self.player_name} {self.stat_type} {self.line}: {'HIT' if self.hit else 'MISS' if self.hit is False else 'PENDING'}>"


# Add back_populates to HistoricalParlay
HistoricalParlay.legs = relationship("HistoricalParlayLeg", back_populates="parlay")



