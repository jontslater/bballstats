#!/usr/bin/env python3
"""
Seed NBA teams into the database.

Usage:
    python scripts/seed_teams.py
"""
import sys
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Team

# NBA Teams data
NBA_TEAMS = [
    {"name": "Atlanta Hawks", "abbreviation": "ATL", "conference": "East", "division": "Southeast"},
    {"name": "Boston Celtics", "abbreviation": "BOS", "conference": "East", "division": "Atlantic"},
    {"name": "Brooklyn Nets", "abbreviation": "BKN", "conference": "East", "division": "Atlantic"},
    {"name": "Charlotte Hornets", "abbreviation": "CHA", "conference": "East", "division": "Southeast"},
    {"name": "Chicago Bulls", "abbreviation": "CHI", "conference": "East", "division": "Central"},
    {"name": "Cleveland Cavaliers", "abbreviation": "CLE", "conference": "East", "division": "Central"},
    {"name": "Dallas Mavericks", "abbreviation": "DAL", "conference": "West", "division": "Southwest"},
    {"name": "Denver Nuggets", "abbreviation": "DEN", "conference": "West", "division": "Northwest"},
    {"name": "Detroit Pistons", "abbreviation": "DET", "conference": "East", "division": "Central"},
    {"name": "Golden State Warriors", "abbreviation": "GSW", "conference": "West", "division": "Pacific"},
    {"name": "Houston Rockets", "abbreviation": "HOU", "conference": "West", "division": "Southwest"},
    {"name": "Indiana Pacers", "abbreviation": "IND", "conference": "East", "division": "Central"},
    {"name": "LA Clippers", "abbreviation": "LAC", "conference": "West", "division": "Pacific"},
    {"name": "Los Angeles Lakers", "abbreviation": "LAL", "conference": "West", "division": "Pacific"},
    {"name": "Memphis Grizzlies", "abbreviation": "MEM", "conference": "West", "division": "Southwest"},
    {"name": "Miami Heat", "abbreviation": "MIA", "conference": "East", "division": "Southeast"},
    {"name": "Milwaukee Bucks", "abbreviation": "MIL", "conference": "East", "division": "Central"},
    {"name": "Minnesota Timberwolves", "abbreviation": "MIN", "conference": "West", "division": "Northwest"},
    {"name": "New Orleans Pelicans", "abbreviation": "NOP", "conference": "West", "division": "Southwest"},
    {"name": "New York Knicks", "abbreviation": "NYK", "conference": "East", "division": "Atlantic"},
    {"name": "Oklahoma City Thunder", "abbreviation": "OKC", "conference": "West", "division": "Northwest"},
    {"name": "Orlando Magic", "abbreviation": "ORL", "conference": "East", "division": "Southeast"},
    {"name": "Philadelphia 76ers", "abbreviation": "PHI", "conference": "East", "division": "Atlantic"},
    {"name": "Phoenix Suns", "abbreviation": "PHX", "conference": "West", "division": "Pacific"},
    {"name": "Portland Trail Blazers", "abbreviation": "POR", "conference": "West", "division": "Northwest"},
    {"name": "Sacramento Kings", "abbreviation": "SAC", "conference": "West", "division": "Pacific"},
    {"name": "San Antonio Spurs", "abbreviation": "SAS", "conference": "West", "division": "Southwest"},
    {"name": "Toronto Raptors", "abbreviation": "TOR", "conference": "East", "division": "Atlantic"},
    {"name": "Utah Jazz", "abbreviation": "UTA", "conference": "West", "division": "Northwest"},
    {"name": "Washington Wizards", "abbreviation": "WAS", "conference": "East", "division": "Southeast"},
]


def seed_teams():
    """Seed teams into the database."""
    db: Session = SessionLocal()
    
    try:
        # Check if teams already exist
        existing_count = db.query(Team).count()
        if existing_count > 0:
            print(f"⚠️  {existing_count} teams already exist in database.")
            response = input("Do you want to continue? This will skip existing teams. (y/n): ")
            if response.lower() != 'y':
                print("Cancelled.")
                return
        
        # Create teams
        created = 0
        skipped = 0
        
        for team_data in NBA_TEAMS:
            # Check if team already exists
            existing = db.query(Team).filter(Team.abbreviation == team_data["abbreviation"]).first()
            
            if existing:
                skipped += 1
                continue
            
            team = Team(**team_data)
            db.add(team)
            created += 1
        
        db.commit()
        
        print(f"✅ Successfully seeded {created} teams")
        if skipped > 0:
            print(f"   (Skipped {skipped} existing teams)")
        
        # Verify
        total = db.query(Team).count()
        print(f"✅ Total teams in database: {total}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding teams: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("🏀 Seeding NBA Teams...")
    print("=" * 50)
    seed_teams()
    print("=" * 50)
    print("✅ Done!")

