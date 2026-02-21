#!/usr/bin/env python3
"""
Seed MLB teams and current season.

Usage:
    PYTHONPATH=backend python scripts/seed_mlb_teams.py
"""
import sys
from pathlib import Path
from datetime import date

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.models import Team, Season


MLB_TEAMS = [
    ('NYY', 'New York Yankees', 'AL', 'East'),
    ('BOS', 'Boston Red Sox', 'AL', 'East'),
    ('TBR', 'Tampa Bay Rays', 'AL', 'East'),
    ('TOR', 'Toronto Blue Jays', 'AL', 'East'),
    ('BAL', 'Baltimore Orioles', 'AL', 'East'),
    ('CLE', 'Cleveland Guardians', 'AL', 'Central'),
    ('CWS', 'Chicago White Sox', 'AL', 'Central'),
    ('DET', 'Detroit Tigers', 'AL', 'Central'),
    ('KCR', 'Kansas City Royals', 'AL', 'Central'),
    ('MIN', 'Minnesota Twins', 'AL', 'Central'),
    ('HOU', 'Houston Astros', 'AL', 'West'),
    ('LAA', 'Los Angeles Angels', 'AL', 'West'),
    ('OAK', 'Oakland Athletics', 'AL', 'West'),
    ('SEA', 'Seattle Mariners', 'AL', 'West'),
    ('TEX', 'Texas Rangers', 'AL', 'West'),
    ('ATL', 'Atlanta Braves', 'NL', 'East'),
    ('MIA', 'Miami Marlins', 'NL', 'East'),
    ('NYM', 'New York Mets', 'NL', 'East'),
    ('PHI', 'Philadelphia Phillies', 'NL', 'East'),
    ('WSN', 'Washington Nationals', 'NL', 'East'),
    ('CHC', 'Chicago Cubs', 'NL', 'Central'),
    ('CIN', 'Cincinnati Reds', 'NL', 'Central'),
    ('MIL', 'Milwaukee Brewers', 'NL', 'Central'),
    ('PIT', 'Pittsburgh Pirates', 'NL', 'Central'),
    ('STL', 'St. Louis Cardinals', 'NL', 'Central'),
    ('ARI', 'Arizona Diamondbacks', 'NL', 'West'),
    ('COL', 'Colorado Rockies', 'NL', 'West'),
    ('LAD', 'Los Angeles Dodgers', 'NL', 'West'),
    ('SDP', 'San Diego Padres', 'NL', 'West'),
    ('SFG', 'San Francisco Giants', 'NL', 'West'),
]


def main():
    db = SessionLocal()
    year = date.today().year
    try:
        for abbr, name, conf, div in MLB_TEAMS:
            existing = db.query(Team).filter(Team.sport == 'MLB', Team.abbreviation == abbr).first()
            if not existing:
                db.add(Team(sport='MLB', name=name, abbreviation=abbr, conference=conf, division=div))
        db.commit()
        print(f"Seeded {len(MLB_TEAMS)} MLB teams")

        season_year = str(year)
        existing_season = db.query(Season).filter(Season.sport == 'MLB', Season.season_year == season_year).first()
        if not existing_season:
            db.add(Season(
                sport='MLB',
                season_year=season_year,
                is_current=True
            ))
            db.commit()
            print(f"Seeded MLB season {season_year}")
        else:
            print(f"MLB season {season_year} already exists")
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
