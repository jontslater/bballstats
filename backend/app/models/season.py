"""
Season model - NBA seasons
"""
from sqlalchemy import Column, Integer, String, Date, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Season(Base):
    __tablename__ = "seasons"

    season_id = Column(Integer, primary_key=True, index=True)
    season_year = Column(String(10), nullable=False, unique=True)  # "2023-24"
    start_date = Column(Date)
    end_date = Column(Date)
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Season {self.season_year}>"


