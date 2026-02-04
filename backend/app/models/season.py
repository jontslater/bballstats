"""
Season model - NBA and NFL seasons
"""
from sqlalchemy import Column, Integer, String, Date, Boolean, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class Season(Base):
    __tablename__ = "seasons"

    season_id = Column(Integer, primary_key=True, index=True)
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL'
    season_year = Column(String(10), nullable=False)  # "2023-24" or "2023"
    start_date = Column(Date)
    end_date = Column(Date)
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Unique constraint: season_year must be unique per sport
    __table_args__ = (UniqueConstraint('sport', 'season_year', name='_sport_season_uc'),)

    def __repr__(self):
        return f"<Season {self.season_year}>"





