#!/usr/bin/env python3
"""Merge duplicate NFL Game rows (±1 day, missing ESPN id)."""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.nfl_game_dedup import dedupe_nfl_games


def main():
    db = SessionLocal()
    try:
        result = dedupe_nfl_games(db)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
