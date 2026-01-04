#!/usr/bin/env python3
"""
Add espn_game_id column to games table.

Run this script to add the espn_game_id column to the games table.
"""
import sys
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import engine, Base
from sqlalchemy import text

def add_espn_game_id_column():
    """Add espn_game_id column to games table if it doesn't exist."""
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='games' AND column_name='espn_game_id'
        """))
        
        if result.fetchone():
            print("✅ Column 'espn_game_id' already exists in 'games' table")
            return
        
        # Add the column
        conn.execute(text("""
            ALTER TABLE games 
            ADD COLUMN espn_game_id VARCHAR(20) UNIQUE
        """))
        
        # Create index
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_games_espn_game_id ON games(espn_game_id)
        """))
        
        conn.commit()
        print("✅ Successfully added 'espn_game_id' column to 'games' table")

if __name__ == "__main__":
    add_espn_game_id_column()


