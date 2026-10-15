"""
Daily Statcast batted-ball rollups per MLBAM batter id.

Built from Baseball Savant game-day CSV exports so walk-forward backtests can
aggregate only events strictly before a prediction date (no season-to-date leakage).
"""
from sqlalchemy import Column, Integer, Float, Date, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func

from app.database import Base


class MlbStatcastDaily(Base):
    __tablename__ = "mlb_statcast_daily"

    id = Column(Integer, primary_key=True, index=True)
    mlbam_id = Column(Integer, nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=True, index=True)
    game_date = Column(Date, nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)

    bip = Column(Integer, nullable=False, default=0)
    hits_on_bip = Column(Integer, nullable=False, default=0)
    total_bases_on_bip = Column(Integer, nullable=False, default=0)
    sum_est_ba = Column(Float, nullable=False, default=0.0)
    sum_est_slg = Column(Float, nullable=False, default=0.0)
    sum_est_woba = Column(Float, nullable=False, default=0.0)
    hard_hit_count = Column(Integer, nullable=False, default=0)
    barrel_count = Column(Integer, nullable=False, default=0)
    launch_speed_sum = Column(Float, nullable=False, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("mlbam_id", "game_date", name="uq_mlb_statcast_daily_mlbam_date"),
        Index("ix_mlb_statcast_daily_season_date", "season", "game_date"),
    )

    def __repr__(self):
        return f"<MlbStatcastDaily mlbam={self.mlbam_id} date={self.game_date} bip={self.bip}>"
