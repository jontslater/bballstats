"""
Persisted out-of-sample NBA prop calibration gates and probability adjustments.
"""
from sqlalchemy import Boolean, Column, DateTime, Float, String, Text
from sqlalchemy.sql import func

from app.database import Base


class NbaPropCalibrationGate(Base):
    __tablename__ = "nba_prop_calibration_gates"

    stat_type = Column(String(40), primary_key=True)
    passes_gate = Column(Boolean, nullable=False, default=False)
    prob_adjustment = Column(Float, nullable=False, default=0.0)
    median_line_p_over = Column(Float, nullable=True)
    brier_score = Column(Float, nullable=True)
    bucket_json = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
