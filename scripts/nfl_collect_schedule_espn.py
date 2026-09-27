#!/usr/bin/env python3
"""
Collect NFL schedules from ESPN API (primary) with Pro Football Reference fallback.

This script uses ESPN's public API which works reliably on Windows without HTTP 403 errors.
Falls back to Pro Football Reference if ESPN is unavailable.

Usage:
    python scripts/nfl_collect_schedule_espn.py --season 2025 --week 1
    python scripts/nfl_collect_schedule_espn.py --season 2025 --all-weeks
"""

import sys
import argparse
from pathlib import Path
from datetime import date

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import GameSchedule, Team, Season
from app.scrapers.espn_nfl_client import ESPNNFLClient


def find_team_by_abbreviation(db: Session, abbreviation: str, sport: str = 'NFL') -> Team:
    """Find team by abbreviation with some common variations."""
    # Try direct match first
    team = db.query(Team).filter(
        Team.sport == sport,
        Team.abbreviation == abbreviation.upper()
    ).first()
    
    if team:
        return team
    
    # Try common ESPN -> our abbreviation mappings
    abbrev_map = {
        'WSH': 'WAS',  # Washington
        # Add more if needed
    }
    
    mapped_abbrev = abbrev_map.get(abbreviation.upper())
    if mapped_abbrev:
        return db.query(Team).filter(
            Team.sport == sport,
            Team.abbreviation == mapped_abbrev
        ).first()
    
    return None


def save_week_schedule(db: Session, games: list, season: Season, week: int):
    """Save games from a week to the database."""
    created = 0
    updated = 0
    errors = 0
    
    for game_data in games:
        try:
            # Find teams
            home_abbrev = game_data.get('home_team_abbrev', '')
            away_abbrev = game_data.get('away_team_abbrev', '')
            
            home_team = find_team_by_abbreviation(db, home_abbrev, 'NFL')
            away_team = find_team_by_abbreviation(db, away_abbrev, 'NFL')
            
            if not home_team or not away_team:
                print(f"  ⚠️  Teams not found: {away_abbrev} @ {home_abbrev}")
                errors += 1
                continue
            
            espn_game_id = game_data.get('espn_game_id', '')
            game_date = game_data.get('game_date')
            game_time = game_data.get('game_time')
            
            if not game_date:
                print(f"  ⚠️  No game date for {away_abbrev} @ {home_abbrev}")
                errors += 1
                continue
            
            # Check if game already exists by external_game_id
            existing = db.query(GameSchedule).filter(
                GameSchedule.sport == 'NFL',
                GameSchedule.external_game_id == espn_game_id
            ).first()
            
            if not existing and espn_game_id:
                # Also check by teams and date (in case we have it without external ID)
                existing = db.query(GameSchedule).filter(
                    GameSchedule.sport == 'NFL',
                    GameSchedule.game_date == game_date,
                    GameSchedule.home_team_id == home_team.team_id,
                    GameSchedule.away_team_id == away_team.team_id
                ).first()
            
            if existing:
                # Update existing record
                existing.game_time = game_time
                existing.external_game_id = espn_game_id or existing.external_game_id
                existing.status = game_data.get('status', 'scheduled')
                updated += 1
                print(f"  ↻ Updated: {away_abbrev} @ {home_abbrev} on {game_date}")
            else:
                # Create new record
                schedule = GameSchedule(
                    sport='NFL',
                    game_date=game_date,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    game_time=game_time,
                    season_id=season.season_id,
                    external_game_id=espn_game_id,
                    status=game_data.get('status', 'scheduled')
                )
                db.add(schedule)
                created += 1
                print(f"  ✓ Added: {away_abbrev} @ {home_abbrev} on {game_date}")
                
        except Exception as e:
            print(f"  ⚠️  Error processing game: {e}")
            errors += 1
            continue
    
    db.commit()
    return created, updated, errors


def collect_week(db: Session, client: ESPNNFLClient, season_year: str, week: int):
    """Collect schedule for a specific week."""
    season = db.query(Season).filter(
        Season.sport == 'NFL',
        Season.season_year == season_year
    ).first()
    
    if not season:
        print(f"❌ Season {season_year} not found")
        return
    
    print(f"📅 Collecting NFL Week {week} schedule for {season_year}...")
    
    # Fetch from ESPN
    games = client.get_week_schedule(int(season_year), week, season_type=2)
    
    if not games:
        print(f"  ⚠️  No games found for week {week}")
        return
    
    print(f"  Found {len(games)} games from ESPN API")
    
    # Save to database
    created, updated, errors = save_week_schedule(db, games, season, week)
    
    print(f"  ✅ Week {week}: {created} created, {updated} updated, {errors} errors")


def collect_season(db: Session, client: ESPNNFLClient, season_year: str):
    """Collect schedule for entire season (all 18 weeks)."""
    season = db.query(Season).filter(
        Season.sport == 'NFL',
        Season.season_year == season_year
    ).first()
    
    if not season:
        print(f"❌ Season {season_year} not found")
        return
    
    print(f"\n📅 Collecting full NFL {season_year} season schedule from ESPN...")
    
    total_created = 0
    total_updated = 0
    total_errors = 0
    
    # NFL regular season: 18 weeks
    for week in range(1, 19):
        games = client.get_week_schedule(int(season_year), week, season_type=2)
        
        if games:
            print(f"  Week {week}: Found {len(games)} games")
            created, updated, errors = save_week_schedule(db, games, season, week)
            total_created += created
            total_updated += updated
            total_errors += errors
        else:
            print(f"  Week {week}: No games found")
    
    print(f"\n✅ Season {season_year} complete:")
    print(f"   Created: {total_created}")
    print(f"   Updated: {total_updated}")
    print(f"   Errors: {total_errors}")


def main():
    parser = argparse.ArgumentParser(description='Collect NFL schedules from ESPN API')
    parser.add_argument('--season', type=str, help='Season year (e.g., "2024")')
    parser.add_argument('--week', type=int, help='Week number (1-18)')
    parser.add_argument('--all-weeks', action='store_true', help='Collect all weeks for season')
    
    args = parser.parse_args()
    
    db: Session = SessionLocal()
    client = ESPNNFLClient(delay=0.5)
    
    try:
        # Default to current season if not specified
        if not args.season:
            current_season = db.query(Season).filter(
                Season.sport == 'NFL',
                Season.is_current == True
            ).first()
            if current_season:
                args.season = current_season.season_year
            else:
                print("❌ No current season found. Please specify --season")
                return
        
        if args.all_weeks or not args.week:
            collect_season(db, client, args.season)
        elif args.week:
            collect_week(db, client, args.season, args.week)
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("🏈 NFL Schedule Collection (ESPN API)")
    print("=" * 60)
    main()
    print("=" * 60)
    print("✅ Done!")
