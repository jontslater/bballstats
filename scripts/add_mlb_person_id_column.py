#!/usr/bin/env python3
"""
Add mlb_person_id column to players table for MLB Stats API personId matching.

Usage:
    PYTHONPATH=backend python scripts/add_mlb_person_id_column.py
"""
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent / 'backend'
sys.path.insert(0, str(backend_path))

from sqlalchemy import text
from app.database import SessionLocal


def main():
    db = SessionLocal()
    try:
        db.execute(text(
            'ALTER TABLE players ADD COLUMN IF NOT EXISTS mlb_person_id INTEGER;'
        ))
        db.execute(text(
            'CREATE INDEX IF NOT EXISTS idx_players_mlb_person_id ON players(mlb_person_id);'
        ))
        db.commit()
        print('mlb_person_id column migration complete.')
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    main()
