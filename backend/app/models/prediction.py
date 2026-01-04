"""
Prediction model - Distribution-based predictions for player performance
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Float, Text, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    prediction_id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    stat_type = Column(String(20), nullable=False)  # points, rebounds, assists, minutes
    
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
    standard_line = Column(Float)
    standard_probability = Column(Float)
    long_shot_line = Column(Float)
    long_shot_probability = Column(Float)
    
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


