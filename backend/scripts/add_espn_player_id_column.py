#!/usr/bin/env python3
"""Add espn_player_id column to players table if missing."""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy import text

from app.database import engine


def main():
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='players' AND column_name='espn_player_id'
        """
            )
        )
        if result.fetchone():
            print("Column espn_player_id already exists")
            return
        conn.execute(text("ALTER TABLE players ADD COLUMN espn_player_id VARCHAR(20)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_players_espn_player_id ON players(espn_player_id)"))
        conn.commit()
        print("Added espn_player_id to players")


if __name__ == "__main__":
    main()
