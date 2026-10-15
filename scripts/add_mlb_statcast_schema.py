#!/usr/bin/env python3
"""
Add MLB Statcast tables/columns for luck adjustment.

Usage (Postgres on owner's desktop, port 5433):
    set DATABASE_URL=postgresql://user:pass@localhost:5433/nba_betting
    PYTHONPATH=backend python scripts/add_mlb_statcast_schema.py
"""
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import text
from app.database import SessionLocal, engine
from app.models import MlbStatcastDaily  # noqa: F401 — register model
from app.database import Base


def migrate(db):
    db.execute(
        text(
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS mlbam_id INTEGER;"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_players_mlbam_id ON players (mlbam_id);"
        )
    )
    db.commit()
    Base.metadata.create_all(bind=engine, tables=[MlbStatcastDaily.__table__])
    print("MLB Statcast schema migration complete.")


def main():
    db = SessionLocal()
    try:
        migrate(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
