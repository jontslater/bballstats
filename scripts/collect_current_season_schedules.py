#!/usr/bin/env python3
"""
Collect NBA schedules for the current season (2024-25) manually.
This bypasses the existing schedule collection that seems to be stuck on old data.
"""

import sys
import os
import requests
import json
from datetime import datetime, date, timedelta
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import GameSchedule, Team, Season

def get_current_season_games():
    """Get games from ESPN API for current season."""
    print("🔍 Fetching current NBA season games from ESPN...")

    # ESPN API for NBA scoreboard
    base_url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

    # Get games for a date range (past 7 days + next 60 days from today)
    start_date = date.today() - timedelta(days=7)
    end_date = date.today() + timedelta(days=60)

    all_games = []
    current_date = start_date

    while current_date <= end_date:
        date_str = current_date.strftime("%Y%m%d")

        try:
            url = f"{base_url}?dates={date_str}"
            print(f"Fetching games for {current_date.strftime('%Y-%m-%d')}...")

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()

            if 'events' in data:
                for event in data['events']:
                    game = {
                        'game_date': current_date,
                        'espn_game_id': event.get('id'),
                        'home_team': None,
                        'away_team': None,
                        'home_team_id': None,
                        'away_team_id': None,
                        'status': 'scheduled'
                    }

                    # Extract team info
                    if 'competitions' in event and event['competitions']:
                        competition = event['competitions'][0]
                        if 'competitors' in competition:
                            for competitor in competition['competitors']:
                                team_name = competitor.get('team', {}).get('abbreviation')
                                if competitor.get('homeAway') == 'home':
                                    game['home_team'] = team_name
                                elif competitor.get('homeAway') == 'away':
                                    game['away_team'] = team_name

                    if game['home_team'] and game['away_team']:
                        all_games.append(game)
                        print(f"  ✓ {game['away_team']} @ {game['home_team']}")

            import time
            time.sleep(0.5)  # Rate limiting

        except Exception as e:
            print(f"  ⚠️ Error fetching {current_date}: {e}")

        current_date += timedelta(days=1)

    print(f"📊 Found {len(all_games)} games")
    return all_games

def save_games_to_db(games):
    """Save games to database."""
    print("💾 Saving games to database...")

    db = SessionLocal()
    try:
        saved_count = 0

        # Get current season
        current_season = db.query(Season).filter(Season.is_current == True).first()
        if not current_season:
            print("❌ No current season found in database")
            return

        print(f"Using season: {current_season.season_year}")

        for game in games:
            # Check if game already exists
            existing = db.query(GameSchedule).filter(
                GameSchedule.game_date == game['game_date'],
                GameSchedule.home_team.has(abbreviation=game['home_team']),
                GameSchedule.away_team.has(abbreviation=game['away_team'])
            ).first()

            if not existing:
                # Find teams
                home_team = db.query(Team).filter(Team.abbreviation == game['home_team']).first()
                away_team = db.query(Team).filter(Team.abbreviation == game['away_team']).first()

                if home_team and away_team:
                    new_game = GameSchedule(
                        season_id=current_season.season_id,
                        game_date=game['game_date'],
                        home_team_id=home_team.team_id,
                        away_team_id=away_team.team_id,
                        nba_game_id=game['espn_game_id'],  # Use nba_game_id field (stores ESPN ID for compatibility)
                        status='scheduled'
                    )

                    db.add(new_game)
                    saved_count += 1
                    print(f"  ✓ Added {game['away_team']} @ {game['home_team']} on {game['game_date']}")

        db.commit()
        print(f"✅ Saved {saved_count} new games to database")

    except Exception as e:
        print(f"❌ Error saving to database: {e}")
        db.rollback()
    finally:
        db.close()

def main():
    """Main function."""
    print("🏀 NBA Current Season Schedule Collection")
    print("=" * 50)

    try:
        # Get games from ESPN
        games = get_current_season_games()

        if games:
            # Save to database
            save_games_to_db(games)
            print("\n🎉 Schedule collection complete!")
        else:
            print("\n❌ No games found to save")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()