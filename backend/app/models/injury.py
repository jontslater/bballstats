"""
Injury model - Player injuries
"""
from sqlalchemy import Column, Integer, ForeignKey, String, Date, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Injury(Base):
    __tablename__ = "injuries"

    injury_id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    injury_date = Column(Date, nullable=False)
    injury_type = Column(String(100))  # "ankle", "knee", etc.
    status = Column(String(20), nullable=False)  # Out, Doubtful, Questionable, Probable, Available
    severity = Column(String(20))  # minor, moderate, severe
    expected_return_date = Column(Date, nullable=True)
    actual_return_date = Column(Date, nullable=True)
    description = Column(Text)
    source = Column(String(100))  # where we got the info
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    player = relationship("Player", back_populates="injuries")

    def __repr__(self):
        return f"<Injury {self.player_id}: {self.status} - {self.injury_type}>"





