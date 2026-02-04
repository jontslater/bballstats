#!/usr/bin/env python3
"""
Seed NFL seasons into the database.

Usage:
    python scripts/nfl_seed_seasons.py
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

# NFL Season data - Update these dates for current season
# NFL season: September - January/February
# Regular season: 17 games, typically Sept - Jan
# Playoffs: January - February
NFL_SEASONS = [
    {
        "season_year": "2023",
        "start_date": date(2023, 9, 7),  # Regular season start
        "end_date": date(2024, 2, 11),  # Super Bowl date
        "is_current": False
    },
    {
        "season_year": "2024",
        "start_date": date(2024, 9, 5),  # Regular season start
        "end_date": date(2025, 2, 9),  # Super Bowl date (approximate)
        "is_current": True  # Update this based on current date
    },
]


def seed_seasons():
    """Seed NFL seasons into the database."""
    db: Session = SessionLocal()
    
    try:
        # Check if NFL seasons already exist
        existing_nfl_count = db.query(Season).filter(Season.sport == 'NFL').count()
        if existing_nfl_count > 0:
            print(f"⚠️  {existing_nfl_count} NFL seasons already exist in database.")
            response = input("Do you want to continue? This will skip existing seasons. (y/n): ")
            if response.lower() != 'y':
                print("Cancelled.")
                return
        
        # Create seasons
        created = 0
        skipped = 0
        
        for season_data in NFL_SEASONS:
            # Check if season already exists (by sport + season_year)
            existing = db.query(Season).filter(
                Season.sport == 'NFL',
                Season.season_year == season_data["season_year"]
            ).first()
            
            if existing:
                skipped += 1
                continue
            
            season = Season(
                sport='NFL',
                **season_data
            )
            db.add(season)
            created += 1
        
        db.commit()
        
        print(f"✅ Successfully seeded {created} NFL seasons")
        if skipped > 0:
            print(f"   (Skipped {skipped} existing seasons)")
        
        # Verify
        total_nfl = db.query(Season).filter(Season.sport == 'NFL').count()
        current_season = db.query(Season).filter(
            Season.sport == 'NFL',
            Season.is_current == True
        ).first()
        
        print(f"✅ Total NFL seasons in database: {total_nfl}")
        if current_season:
            print(f"✅ Current NFL season: {current_season.season_year}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding NFL seasons: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("🏈 Seeding NFL Seasons...")
    print("=" * 50)
    seed_seasons()
    print("=" * 50)
    print("✅ Done!")

