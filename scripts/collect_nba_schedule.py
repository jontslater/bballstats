#!/usr/bin/env python3
"""
Collect NBA schedules from NBA.com official API.
This replaces the broken ESPN scraper.
"""

import sys
import os
import requests
import json
import time
from datetime import datetime, date, timedelta
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import GameSchedule, Team, Season

def fetch_nba_schedule(year: int = 2025):
    """Fetch NBA schedule from NBA CDN API."""
    print("📅 Fetching NBA schedule from NBA CDN API...")

    url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"

    # Enhanced headers to avoid 403 blocks
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none'
    }

    # Retry with exponential backoff
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            # Handle 403 specifically
            if response.status_code == 403:
                print(f"⚠️  HTTP 403 Forbidden from NBA CDN (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    wait_time = 4 * (2 ** attempt)
                    print(f"⏳ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    print("❌ All retries exhausted. NBA CDN may be blocking requests.")
                    print("💡 You may need to run this from a different network or use a VPN.")
                    return []
            
            response.raise_for_status()
            data = response.json()
        games = []

        # Parse the schedule data
        for game_date_data in data.get('leagueSchedule', {}).get('gameDates', []):
            try:
                # Parse game date - format: "10/02/2025 00:00:00"
                date_str = game_date_data.get('gameDate', '').split(' ')[0]  # Get "10/02/2025"
                if not date_str:
                    continue

                # Convert MM/DD/YYYY to YYYY-MM-DD
                month, day, year_str = date_str.split('/')
                game_date = date(int(year_str), int(month), int(day))

                # Get games for this date
                for game in game_date_data.get('games', []):
                    try:
                        # Get team codes
                        home_team_code = game.get('homeTeam', {}).get('teamTricode', '')
                        away_team_code = game.get('awayTeam', {}).get('teamTricode', '')

                        if not home_team_code or not away_team_code:
                            continue

                        # Get game ID
                        game_id = str(game.get('gameId', ''))

                        games.append({
                            'game_date': game_date,
                            'home_team': home_team_code,
                            'away_team': away_team_code,
                            'nba_game_id': game_id,
                            'status': 'scheduled'
                        })

                    except Exception as e:
                        print(f"⚠️ Error parsing individual game: {e}")
                        continue

            except Exception as e:
                print(f"⚠️ Error parsing game date: {e}")
                continue

            print(f"✅ Found {len(games)} games")
            return games
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 4 * (2 ** attempt)
                print(f"⚠️  Request error (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                print(f"❌ Error fetching schedule after {max_retries} attempts: {e}")
                return []
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing JSON response: {e}")
            print(f"Response content preview: {response.text[:200]}")
            return []
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    return []

def save_games_to_db(games):
    """Save games to database."""
    print("💾 Saving games to database...")

    db = SessionLocal()
    try:
        saved_count = 0

        # Get current season
        current_season = db.query(Season).filter(Season.is_current == True).first()
        if not current_season:
            print("❌ No current season found")
            return

        print(f"Using season: {current_season.season_year}")

        for game in games:
            # Check if game already exists by nba_game_id (most reliable)
            existing = db.query(GameSchedule).filter(
                GameSchedule.nba_game_id == game['nba_game_id']
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
                        nba_game_id=game['nba_game_id'],
                        status='scheduled'
                    )

                    db.add(new_game)
                    saved_count += 1
                    print(f"  ✓ Added {game['away_team']} @ {game['home_team']} on {game['game_date']}")
                else:
                    print(f"  ⚠️ Teams not found: {game['home_team']}, {game['away_team']}")
            else:
                print(f"  - Game already exists: {game['away_team']} @ {game['home_team']} on {game['game_date']}")

        db.commit()
        print(f"✅ Saved {saved_count} new games to database")

    except Exception as e:
        print(f"❌ Error saving to database: {e}")
        db.rollback()
    finally:
        db.close()

def main():
    """Main function."""
    print("🏀 NBA Official Schedule Collection")
    print("=" * 50)

    try:
        # Fetch schedule from NBA.com
        games = fetch_nba_schedule(2025)

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