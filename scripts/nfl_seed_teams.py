#!/usr/bin/env python3
"""
Seed NFL teams into the database.

Usage:
    python scripts/nfl_seed_teams.py
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

# NFL Teams data (32 teams)
NFL_TEAMS = [
    {"name": "Arizona Cardinals", "abbreviation": "ARI", "conference": "NFC", "division": "West"},
    {"name": "Atlanta Falcons", "abbreviation": "ATL", "conference": "NFC", "division": "South"},
    {"name": "Baltimore Ravens", "abbreviation": "BAL", "conference": "AFC", "division": "North"},
    {"name": "Buffalo Bills", "abbreviation": "BUF", "conference": "AFC", "division": "East"},
    {"name": "Carolina Panthers", "abbreviation": "CAR", "conference": "NFC", "division": "South"},
    {"name": "Chicago Bears", "abbreviation": "CHI", "conference": "NFC", "division": "North"},
    {"name": "Cincinnati Bengals", "abbreviation": "CIN", "conference": "AFC", "division": "North"},
    {"name": "Cleveland Browns", "abbreviation": "CLE", "conference": "AFC", "division": "North"},
    {"name": "Dallas Cowboys", "abbreviation": "DAL", "conference": "NFC", "division": "East"},
    {"name": "Denver Broncos", "abbreviation": "DEN", "conference": "AFC", "division": "West"},
    {"name": "Detroit Lions", "abbreviation": "DET", "conference": "NFC", "division": "North"},
    {"name": "Green Bay Packers", "abbreviation": "GB", "conference": "NFC", "division": "North"},
    {"name": "Houston Texans", "abbreviation": "HOU", "conference": "AFC", "division": "South"},
    {"name": "Indianapolis Colts", "abbreviation": "IND", "conference": "AFC", "division": "South"},
    {"name": "Jacksonville Jaguars", "abbreviation": "JAX", "conference": "AFC", "division": "South"},
    {"name": "Kansas City Chiefs", "abbreviation": "KC", "conference": "AFC", "division": "West"},
    {"name": "Las Vegas Raiders", "abbreviation": "LV", "conference": "AFC", "division": "West"},
    {"name": "Los Angeles Chargers", "abbreviation": "LAC", "conference": "AFC", "division": "West"},
    {"name": "Los Angeles Rams", "abbreviation": "LAR", "conference": "NFC", "division": "West"},
    {"name": "Miami Dolphins", "abbreviation": "MIA", "conference": "AFC", "division": "East"},
    {"name": "Minnesota Vikings", "abbreviation": "MIN", "conference": "NFC", "division": "North"},
    {"name": "New England Patriots", "abbreviation": "NE", "conference": "AFC", "division": "East"},
    {"name": "New Orleans Saints", "abbreviation": "NO", "conference": "NFC", "division": "South"},
    {"name": "New York Giants", "abbreviation": "NYG", "conference": "NFC", "division": "East"},
    {"name": "New York Jets", "abbreviation": "NYJ", "conference": "AFC", "division": "East"},
    {"name": "Philadelphia Eagles", "abbreviation": "PHI", "conference": "NFC", "division": "East"},
    {"name": "Pittsburgh Steelers", "abbreviation": "PIT", "conference": "AFC", "division": "North"},
    {"name": "San Francisco 49ers", "abbreviation": "SF", "conference": "NFC", "division": "West"},
    {"name": "Seattle Seahawks", "abbreviation": "SEA", "conference": "NFC", "division": "West"},
    {"name": "Tampa Bay Buccaneers", "abbreviation": "TB", "conference": "NFC", "division": "South"},
    {"name": "Tennessee Titans", "abbreviation": "TEN", "conference": "AFC", "division": "South"},
    {"name": "Washington Commanders", "abbreviation": "WAS", "conference": "NFC", "division": "East"},
]


def seed_teams():
    """Seed NFL teams into the database."""
    db: Session = SessionLocal()
    
    try:
        # Check if NFL teams already exist
        existing_nfl_count = db.query(Team).filter(Team.sport == 'NFL').count()
        if existing_nfl_count > 0:
            print(f"⚠️  {existing_nfl_count} NFL teams already exist in database.")
            response = input("Do you want to continue? This will skip existing teams. (y/n): ")
            if response.lower() != 'y':
                print("Cancelled.")
                return
        
        # Create teams one at a time (to handle duplicates gracefully)
        created = 0
        skipped = 0
        errors = 0
        
        for team_data in NFL_TEAMS:
            try:
                # Check if team already exists (by sport + abbreviation)
                existing = db.query(Team).filter(
                    Team.sport == 'NFL',
                    Team.abbreviation == team_data["abbreviation"]
                ).first()
                
                if existing:
                    skipped += 1
                    continue
                
                team = Team(
                    sport='NFL',
                    **team_data
                )
                db.add(team)
                db.flush()  # Flush to check for constraint violations immediately
                created += 1
            except Exception as e:
                db.rollback()
                # Check if it's a duplicate constraint error
                if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
                    skipped += 1
                    print(f"  ⚠️  Team {team_data['abbreviation']} already exists (possibly from NBA)")
                else:
                    errors += 1
                    print(f"  ❌ Error adding {team_data['abbreviation']}: {e}")
        
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"❌ Error committing teams: {e}")
            raise
        
        print(f"✅ Successfully seeded {created} NFL teams")
        if skipped > 0:
            print(f"   (Skipped {skipped} existing teams)")
        
        # Verify
        total_nfl = db.query(Team).filter(Team.sport == 'NFL').count()
        print(f"✅ Total NFL teams in database: {total_nfl}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding NFL teams: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("🏈 Seeding NFL Teams...")
    print("=" * 50)
    seed_teams()
    print("=" * 50)
    print("✅ Done!")

