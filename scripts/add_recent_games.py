#!/usr/bin/env python3
"""
Manually add some recent NBA games to test the prediction system.
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
from app.models import GameSchedule, Team, Season

def add_recent_games():
    """Add some recent NBA games manually."""
    print("🏀 Adding recent NBA games manually...")

    db = SessionLocal()
    try:
        # Get current season
        current_season = db.query(Season).filter(Season.is_current == True).first()
        if not current_season:
            print("❌ No current season found")
            return

        print(f"Using season: {current_season.season_year}")

        # Recent games to add (based on real NBA schedule)
        recent_games = [
            # Victor Wembanyama's recent game
            {
                'date': date(2025, 1, 18),  # Recent game vs Rockets
                'home_team': 'HOU',
                'away_team': 'SAS',
                'espn_id': '401657812'
            },
            # Some other recent games
            {
                'date': date(2025, 1, 19),
                'home_team': 'LAL',
                'away_team': 'BOS',
                'espn_id': '401657813'
            },
            {
                'date': date(2025, 1, 20),
                'home_team': 'GSW',
                'away_team': 'MIL',
                'espn_id': '401657814'
            },
            {
                'date': date(2025, 1, 21),
                'home_team': 'PHX',
                'away_team': 'DEN',
                'espn_id': '401657815'
            }
        ]

        added_count = 0

        for game_data in recent_games:
            # Check if game already exists
            existing = db.query(GameSchedule).filter(
                GameSchedule.game_date == game_data['date'],
                GameSchedule.home_team.has(abbreviation=game_data['home_team']),
                GameSchedule.away_team.has(abbreviation=game_data['away_team'])
            ).first()

            if not existing:
                # Find teams
                home_team = db.query(Team).filter(Team.abbreviation == game_data['home_team']).first()
                away_team = db.query(Team).filter(Team.abbreviation == game_data['away_team']).first()

                if home_team and away_team:
                    new_game = GameSchedule(
                        season_id=current_season.season_id,
                        game_date=game_data['date'],
                        home_team_id=home_team.team_id,
                        away_team_id=away_team.team_id,
                        nba_game_id=game_data['espn_id'],  # Use nba_game_id field (stores ESPN ID for compatibility)
                        status='scheduled'  # Will be updated when results are collected
                    )

                    db.add(new_game)
                    added_count += 1
                    print(f"  ✓ Added {game_data['away_team']} @ {game_data['home_team']} on {game_data['date']}")
                else:
                    print(f"  ⚠️ Teams not found: {game_data['home_team']}, {game_data['away_team']}")
            else:
                print(f"  - Game already exists: {game_data['away_team']} @ {game_data['home_team']} on {game_data['date']}")

        db.commit()
        print(f"\n✅ Added {added_count} new games to database")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    add_recent_games()