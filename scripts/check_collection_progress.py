#!/usr/bin/env python3
"""
Quick script to check collection progress.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.models.game import Game
from app.models.player_game_stat import PlayerGameStat
from sqlalchemy import func

db = SessionLocal()
try:
    # Game stats
    total_games = db.query(Game).count()
    date_range = db.query(func.min(Game.game_date), func.max(Game.game_date)).first()
    unique_dates = db.query(func.count(func.distinct(Game.game_date))).scalar()
    
    # Player stats
    total_stats = db.query(PlayerGameStat).count()
    unique_players = db.query(func.count(func.distinct(PlayerGameStat.player_id))).scalar()
    
    # Games per player (using subquery)
    from sqlalchemy import select
    subquery = db.query(
        PlayerGameStat.player_id,
        func.count(PlayerGameStat.stat_id).label('game_count')
    ).group_by(PlayerGameStat.player_id).subquery()
    
    avg_games_per_player = db.query(func.avg(subquery.c.game_count)).scalar()
    
    print("📊 Collection Progress")
    print("=" * 60)
    print(f"Total Games: {total_games}")
    print(f"Unique Dates: {unique_dates}")
    if date_range[0]:
        print(f"Date Range: {date_range[0]} to {date_range[1]}")
    print()
    print(f"Total Player Stats: {total_stats:,}")
    print(f"Unique Players: {unique_players}")
    if avg_games_per_player:
        print(f"Avg Games per Player: {avg_games_per_player:.1f}")
    print("=" * 60)
    
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()

