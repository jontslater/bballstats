#!/usr/bin/env python3
"""
Add external_game_id column to game_schedules table.

This is a sport-agnostic replacement for nba_game_id (which was being abused for NFL).
Run this script to add the external_game_id column and migrate existing data.
"""
import sys
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import engine
from sqlalchemy import text


def add_external_game_id_column():
    """Add external_game_id column and migrate existing data."""
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='game_schedules' AND column_name='external_game_id'
        """))
        
        if result.fetchone():
            print("✅ Column 'external_game_id' already exists in 'game_schedules' table")
            return
        
        print("Adding 'external_game_id' column to 'game_schedules' table...")
        
        # Add the column
        conn.execute(text("""
            ALTER TABLE game_schedules 
            ADD COLUMN external_game_id VARCHAR(50)
        """))
        
        # Migrate existing nba_game_id values to external_game_id
        print("Migrating existing nba_game_id values to external_game_id...")
        conn.execute(text("""
            UPDATE game_schedules
            SET external_game_id = nba_game_id
            WHERE nba_game_id IS NOT NULL AND external_game_id IS NULL
        """))
        
        # Create index
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_game_schedules_external_game_id 
            ON game_schedules(external_game_id)
        """))
        
        conn.commit()
        print("✅ Successfully added 'external_game_id' column and migrated data")
        print("   Note: nba_game_id column is kept for backward compatibility but deprecated")


if __name__ == "__main__":
    add_external_game_id_column()
