#!/usr/bin/env python3
"""
Migration script to add confidence and line source columns to predictions table.

Adds:
- line_source (VARCHAR): 'sportsbook' or 'model'
- confidence_score (REAL): numerical confidence score 0-100
- confidence_reasons (TEXT): JSON array of confidence reason strings
- data_as_of (TIMESTAMP): when the data used for prediction was last updated
- n_games_effective (REAL): effective sample size after Empirical Bayes adjustment

Usage:
    PYTHONPATH=backend python scripts/add_prediction_confidence_columns.py
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import text
from app.database import SessionLocal


def add_prediction_columns(db):
    """Add new confidence and line source columns to predictions table."""
    columns = [
        ("line_source", "VARCHAR(20) DEFAULT 'model'"),
        ("confidence_score", "REAL"),
        ("confidence_reasons", "TEXT"),  # JSON array
        ("data_as_of", "TIMESTAMP"),
        ("n_games_effective", "REAL"),
    ]
    
    for col_name, col_definition in columns:
        try:
            db.execute(text(
                f"ALTER TABLE predictions ADD COLUMN IF NOT EXISTS {col_name} {col_definition};"
            ))
            print(f"  ✅ Added column: {col_name}")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"  ℹ️  Column {col_name} already exists")
            else:
                raise
    
    db.commit()
    print("✅ Prediction confidence columns migration complete.")


def main():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("Adding confidence columns to predictions table...")
        print("=" * 60)
        add_prediction_columns(db)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
