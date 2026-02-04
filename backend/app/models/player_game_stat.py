"""
PlayerGameStat model - Individual player statistics per game (NBA and NFL)
"""
from sqlalchemy import Column, Integer, ForeignKey, Boolean, Float, DateTime, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PlayerGameStat(Base):
    __tablename__ = "player_game_stats"

    stat_id = Column(Integer, primary_key=True, index=True)
    sport = Column(String(10), nullable=False, default='NBA', index=True)  # 'NBA' or 'NFL'
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    opponent_team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    
    # === NBA Stats ===
    minutes_played = Column(Integer, nullable=True)  # NBA
    points = Column(Integer, nullable=True)
    rebounds = Column(Integer, nullable=True)
    offensive_rebounds = Column(Integer, nullable=True)
    defensive_rebounds = Column(Integer, nullable=True)
    assists = Column(Integer, nullable=True)
    steals = Column(Integer, nullable=True)
    blocks = Column(Integer, nullable=True)
    turnovers = Column(Integer, nullable=True)
    personal_fouls = Column(Integer, nullable=True)
    
    # Shooting stats (NBA)
    field_goals_made = Column(Integer, nullable=True)
    field_goals_attempted = Column(Integer, nullable=True)
    three_pointers_made = Column(Integer, nullable=True)
    three_pointers_attempted = Column(Integer, nullable=True)
    free_throws_made = Column(Integer, nullable=True)
    free_throws_attempted = Column(Integer, nullable=True)
    
    # Advanced stats (NBA)
    plus_minus = Column(Integer, nullable=True)
    usage_rate = Column(Float, nullable=True)
    
    # === NFL Stats ===
    # Passing (QB)
    passing_yards = Column(Integer, nullable=True)
    passing_tds = Column(Integer, nullable=True)
    interceptions = Column(Integer, nullable=True)
    completions = Column(Integer, nullable=True)
    pass_attempts = Column(Integer, nullable=True)
    passer_rating = Column(Float, nullable=True)
    qb_rush_yards = Column(Integer, nullable=True)
    qb_rush_tds = Column(Integer, nullable=True)
    
    # Rushing (RB/QB/WR)
    rushing_yards = Column(Integer, nullable=True)
    rushing_tds = Column(Integer, nullable=True)
    rushing_attempts = Column(Integer, nullable=True)
    fumbles = Column(Integer, nullable=True)
    fumbles_lost = Column(Integer, nullable=True)
    
    # Receiving (WR/TE/RB)
    receptions = Column(Integer, nullable=True)
    receiving_yards = Column(Integer, nullable=True)
    receiving_tds = Column(Integer, nullable=True)
    targets = Column(Integer, nullable=True)
    
    # Playing time (NFL)
    snaps_played = Column(Integer, nullable=True)
    snap_percentage = Column(Float, nullable=True)
    
    # Context
    is_home = Column(Boolean)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    player = relationship("Player", back_populates="game_stats")
    game = relationship("Game", back_populates="player_stats")
    team = relationship("Team", foreign_keys=[team_id])
    opponent_team = relationship("Team", foreign_keys=[opponent_team_id])

    # Unique constraint - one stat record per player per game
    __table_args__ = (UniqueConstraint('player_id', 'game_id', name='_player_game_uc'),)

    def __repr__(self):
        return f"<PlayerGameStat {self.player_id} in game {self.game_id}: {self.points}P/{self.rebounds}R/{self.assists}A>"





