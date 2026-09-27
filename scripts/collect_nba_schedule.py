#!/usr/bin/env python3
"""
Collect NBA schedules from NBA.com official API.
This replaces the broken ESPN scraper.
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

def fetch_nba_schedule_espn(year: int = 2025):
    """Fetch NBA schedule from ESPN API as fallback."""
    print("📅 Attempting ESPN API fallback for NBA schedule...")
    
    try:
        # ESPN doesn't have a single endpoint for full season, so we'll need to aggregate
        # For now, use their scoreboard API for recent/current games
        from datetime import timedelta
        
        games = []
        # Try to get games for the current season window (Oct through June)
        start_date = date(year, 10, 1)  # Season typically starts in October
        end_date = date(year + 1, 6, 30)  # Through June (playoffs)
        
        # Sample a few key dates to get schedule data (full scrape would take too long)
        sample_dates = []
        current = start_date
        while current <= end_date and len(sample_dates) < 30:  # Sample ~30 dates
            sample_dates.append(current)
            current += timedelta(days=7)  # Weekly samples
        
        for game_date in sample_dates:
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
            params = {'dates': game_date.strftime('%Y%m%d')}
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            for event in data.get('events', []):
                try:
                    competitions = event.get('competitions', [{}])
                    if not competitions:
                        continue
                    
                    competitors = competitions[0].get('competitors', [])
                    if len(competitors) < 2:
                        continue
                    
                    # ESPN returns home first, then away
                    home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                    away = next((c for c in competitors if c.get('homeAway') == 'away'), None)
                    
                    if not home or not away:
                        continue
                    
                    games.append({
                        'game_date': game_date,
                        'home_team': home.get('team', {}).get('abbreviation', ''),
                        'away_team': away.get('team', {}).get('abbreviation', ''),
                        'nba_game_id': event.get('id', ''),
                        'status': 'scheduled'
                    })
                except Exception as e:
                    print(f"⚠️ Error parsing ESPN event: {e}")
                    continue
        
        print(f"✅ ESPN API: Found {len(games)} games")
        return games
        
    except Exception as e:
        print(f"⚠️ ESPN API fallback failed: {e}")
        return []


def fetch_nba_schedule(year: int = 2025):
    """Fetch NBA schedule from NBA CDN API with retry and ESPN fallback."""
    print("📅 Fetching NBA schedule from NBA CDN API...")

    url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    
    # Enhanced headers to mimic browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
    }

    # Try with exponential backoff
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                delay = 2 ** attempt  # 2s, 4s, 8s
                print(f"  Retry {attempt + 1}/{max_retries} after {delay}s delay...")
                import time
                time.sleep(delay)
            
            response = requests.get(url, headers=headers, timeout=30)
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

            print(f"✅ Found {len(games)} games from NBA CDN")
            return games

        except requests.HTTPError as e:
            if e.response.status_code == 403:
                print(f"⚠️ HTTP 403 from NBA CDN (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    print("  NBA CDN is blocking requests - trying ESPN fallback...")
                    return fetch_nba_schedule_espn(year)
            else:
                print(f"⚠️ HTTP error: {e}")
                if attempt == max_retries - 1:
                    print("  Trying ESPN fallback...")
                    return fetch_nba_schedule_espn(year)
        except Exception as e:
            print(f"⚠️ Error fetching schedule: {e}")
            if attempt == max_retries - 1:
                print("  Trying ESPN fallback...")
                return fetch_nba_schedule_espn(year)
    
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