#!/usr/bin/env python3
"""
Seed NBA seasons into the database.

Usage:
    python scripts/seed_seasons.py
"""
import sys
from pathlib import Path
from datetime import date

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Season

# Season data - Update these dates for current season
SEASONS = [
    {
        "season_year": "2023-24",
        "start_date": date(2023, 10, 24),
        "end_date": date(2024, 4, 14),
        "is_current": False  # Update this based on current date
    },
    {
        "season_year": "2024-25",
        "start_date": date(2024, 10, 22),
        "end_date": date(2025, 4, 13),
        "is_current": True  # Update this based on current date
    },
]


def seed_seasons():
    """Seed seasons into the database."""
    db: Session = SessionLocal()
    
    try:
        # Check if seasons already exist
        existing_count = db.query(Season).count()
        if existing_count > 0:
            print(f"⚠️  {existing_count} seasons already exist in database.")
            response = input("Do you want to continue? This will skip existing seasons. (y/n): ")
            if response.lower() != 'y':
                print("Cancelled.")
                return
        
        # Create seasons
        created = 0
        skipped = 0
        
        for season_data in SEASONS:
            # Check if season already exists
            existing = db.query(Season).filter(
                Season.season_year == season_data["season_year"]
            ).first()
            
            if existing:
                skipped += 1
                continue
            
            season = Season(**season_data)
            db.add(season)
            created += 1
        
        db.commit()
        
        print(f"✅ Successfully seeded {created} seasons")
        if skipped > 0:
            print(f"   (Skipped {skipped} existing seasons)")
        
        # Verify
        total = db.query(Season).count()
        current_season = db.query(Season).filter(Season.is_current == True).first()
        
        print(f"✅ Total seasons in database: {total}")
        if current_season:
            print(f"✅ Current season: {current_season.season_year}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding seasons: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("🏀 Seeding NBA Seasons...")
    print("=" * 50)
    seed_seasons()
    print("=" * 50)
    print("✅ Done!")

