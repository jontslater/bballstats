"""
PlayerGameStat model - Individual player statistics per game
"""
from sqlalchemy import Column, Integer, ForeignKey, Boolean, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PlayerGameStat(Base):
    __tablename__ = "player_game_stats"

    stat_id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    opponent_team_id = Column(Integer, ForeignKey("teams.team_id"), nullable=False)
    
    # Basic stats
    minutes_played = Column(Integer)
    points = Column(Integer)
    rebounds = Column(Integer)
    offensive_rebounds = Column(Integer)
    defensive_rebounds = Column(Integer)
    assists = Column(Integer)
    steals = Column(Integer)
    blocks = Column(Integer)
    turnovers = Column(Integer)
    personal_fouls = Column(Integer)
    
    # Shooting stats
    field_goals_made = Column(Integer)
    field_goals_attempted = Column(Integer)
    three_pointers_made = Column(Integer)
    three_pointers_attempted = Column(Integer)
    free_throws_made = Column(Integer)
    free_throws_attempted = Column(Integer)
    
    # Advanced stats
    plus_minus = Column(Integer)
    usage_rate = Column(Float)
    
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


