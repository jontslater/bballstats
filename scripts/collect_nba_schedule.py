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


def fetch_nba_schedule_espn(year: int = 2025):
    """
    Fetch NBA schedule from ESPN API as a fallback.
    ESPN API endpoint for NBA schedule: https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard
    """
    print("📅 Fetching NBA schedule from ESPN API (fallback)...")
    
    games = []
    
    try:
        # ESPN scoreboard API - fetch date range
        # We'll try to get games for the season by iterating through dates
        # For a full season approach, we'd need to call this for each date or use their season calendar
        
        # Try the calendar endpoint first for full season
        calendar_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={year}"
        response = requests.get(calendar_url, timeout=30)
        
        if response.status_code == 403:
            print("⚠️  ESPN API returned 403 Forbidden - rate limited or blocked")
            return []
        
        response.raise_for_status()
        data = response.json()
        
        # Parse events (games)
        for event in data.get('events', []):
            try:
                # Get game date
                date_str = event.get('date', '')  # ISO format: "2025-10-22T23:00Z"
                if not date_str:
                    continue
                
                game_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
                
                # Get teams
                competitions = event.get('competitions', [])
                if not competitions:
                    continue
                
                competition = competitions[0]
                competitors = competition.get('competitors', [])
                
                if len(competitors) < 2:
                    continue
                
                # ESPN format: competitors[0] is home, competitors[1] is away (or vice versa based on 'homeAway' field)
                home_team = None
                away_team = None
                
                for competitor in competitors:
                    team_abbrev = competitor.get('team', {}).get('abbreviation', '')
                    home_away = competitor.get('homeAway', '')
                    
                    if home_away == 'home':
                        home_team = team_abbrev
                    elif home_away == 'away':
                        away_team = team_abbrev
                
                if not home_team or not away_team:
                    continue
                
                # Get ESPN game ID
                espn_game_id = event.get('id', '')
                
                games.append({
                    'game_date': game_date,
                    'home_team': home_team,
                    'away_team': away_team,
                    'nba_game_id': espn_game_id,
                    'status': 'scheduled'
                })
                
            except Exception as e:
                print(f"⚠️ Error parsing ESPN game: {e}")
                continue
        
        print(f"✅ ESPN: Found {len(games)} games")
        return games
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print(f"❌ ESPN API blocked with 403 - rate limited")
        else:
            print(f"❌ ESPN API error: {e}")
        return []
    except Exception as e:
        print(f"❌ Error fetching ESPN schedule: {e}")
        return []


def fetch_nba_schedule(year: int = 2025):
    """Fetch NBA schedule from NBA CDN API with ESPN fallback."""
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
            
            # Handle 403 specifically - try ESPN fallback
            if response.status_code == 403:
                print(f"⚠️  HTTP 403 Forbidden from NBA CDN (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    wait_time = 4 * (2 ** attempt)
                    print(f"⏳ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    print("❌ All retries exhausted. Trying ESPN fallback...")
                    return fetch_nba_schedule_espn(year)
            
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
                print(f"❌ Error fetching schedule after {max_retries} attempts. Trying ESPN fallback...")
                return fetch_nba_schedule_espn(year)
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing JSON response: {e}")
            print(f"Response content preview: {response.text[:200]}")
            print("⚠️  Trying ESPN fallback...")
            return fetch_nba_schedule_espn(year)
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            print("⚠️  Trying ESPN fallback...")
            return fetch_nba_schedule_espn(year)
    
    # If all retries failed
    print("⚠️  All attempts failed. Trying ESPN fallback...")
    return fetch_nba_schedule_espn(year)

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
            # Check if game already exists by external_game_id (or fallback to nba_game_id)
            existing = db.query(GameSchedule).filter(
                GameSchedule.external_game_id == game['nba_game_id']
            ).first()
            
            if not existing:
                # Fallback check using old nba_game_id column
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
                        external_game_id=game['nba_game_id'],
                        nba_game_id=game['nba_game_id'],  # Keep for backward compat
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