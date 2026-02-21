#!/usr/bin/env python3
"""
Migration script to add MLB columns to player_game_stats table.

Usage:
    cd backend && python -c "
    import sys; sys.path.insert(0, '.')
    exec(open('../scripts/add_mlb_columns.py').read())
    "
    Or: PYTHONPATH=backend python scripts/add_mlb_columns.py
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import text
from app.database import SessionLocal


def add_mlb_columns(db):
    """Add MLB columns to player_game_stats table."""
    columns = [
        ("hits", "INTEGER"),
        ("home_runs", "INTEGER"),
        ("total_bases", "INTEGER"),
        ("doubles", "INTEGER"),
        ("triples", "INTEGER"),
        ("at_bats", "INTEGER"),
        ("plate_appearances", "INTEGER"),
        ("rbis", "INTEGER"),
        ("strikeouts", "INTEGER"),
        ("innings_pitched", "REAL"),
        ("walks_allowed", "INTEGER"),
        ("hits_allowed", "INTEGER"),
    ]
    for col_name, col_type in columns:
        try:
            db.execute(text(
                f"ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
            ))
            print(f"  Added column: {col_name}")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"  Column {col_name} already exists")
            else:
                raise
    db.commit()
    print("MLB columns migration complete.")


def main():
    db = SessionLocal()
    try:
        add_mlb_columns(db)
    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
