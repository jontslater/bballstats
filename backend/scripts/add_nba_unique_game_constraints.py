#!/usr/bin/env python3
"""Add unique constraints for NBA game ids (sport + espn_game_id / external_game_id)."""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy import inspect, text

from app.database import engine


def main():
    insp = inspect(engine)
    with engine.connect() as conn:
        if insp.has_table("games"):
            exists = conn.execute(
                text(
                    "SELECT 1 FROM pg_constraint WHERE conname = 'uq_games_sport_espn_game_id'"
                )
            ).fetchone()
            if not exists:
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_games_sport_espn_game_id "
                        "ON games (sport, espn_game_id) WHERE espn_game_id IS NOT NULL"
                    )
                )
        if insp.has_table("game_schedules"):
            exists = conn.execute(
                text(
                    "SELECT 1 FROM pg_constraint WHERE conname = 'uq_game_schedules_sport_external_game_id'"
                )
            ).fetchone()
            if not exists:
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_game_schedules_sport_external_game_id "
                        "ON game_schedules (sport, external_game_id) WHERE external_game_id IS NOT NULL"
                    )
                )
        conn.commit()
    print("NBA unique game id indexes applied (or already present)")


if __name__ == "__main__":
    main()
