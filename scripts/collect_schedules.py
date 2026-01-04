#!/usr/bin/env python3
"""
Collect and store NBA game schedules from NBA API.

Usage:
    python scripts/collect_schedules.py [--season SEASON] [--date DATE]
"""
import sys
from pathlib import Path
from datetime import datetime, date, timedelta

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models import GameSchedule, Team, Season
from app.scrapers.nba_api_client import NBAAPIClient


def find_team_by_id(db: Session, nba_team_id: int):
    """Find team by NBA API team ID."""
    # NBA API uses different IDs than our database
    # We'll need to map them - for now, try to find by abbreviation
    return None  # TODO: Implement team ID mapping


def find_team_by_nba_id(db: Session, nba_team_id: int):
    """Find team by NBA API team ID using abbreviation mapping."""
    # NBA API team IDs to abbreviations mapping
    # This is a simplified mapping - you may need to update this
    team_id_map = {
        1610612737: "ATL", 1610612738: "BOS", 1610612751: "BKN",
        1610612766: "CHA", 1610612741: "CHI", 1610612739: "CLE",
        1610612742: "DAL", 1610612743: "DEN", 1610612765: "DET",
        1610612744: "GSW", 1610612745: "HOU", 1610612754: "IND",
        1610612746: "LAC", 1610612747: "LAL", 1610612763: "MEM",
        1610612748: "MIA", 1610612749: "MIL", 1610612750: "MIN",
        1610612740: "NOP", 1610612752: "NYK", 1610612760: "OKC",
        1610612753: "ORL", 1610612755: "PHI", 1610612756: "PHX",
        1610612757: "POR", 1610612758: "SAC", 1610612759: "SAS",
        1610612761: "TOR", 1610612762: "UTA", 1610612764: "WAS"
    }
    
    abbrev = team_id_map.get(nba_team_id)
    if abbrev:
        return db.query(Team).filter(Team.abbreviation == abbrev).first()
    return None


def collect_schedule_for_date(db: Session, client: NBAAPIClient, game_date: date, season: Season):
    """Collect schedule for a specific date."""
    games_data = client.get_game_schedule(game_date)
    
    # Deduplicate by NBA game ID to avoid processing the same game twice
    seen_game_ids = set()
    unique_games = []
    for game_data in games_data:
        game_id = game_data.get('GAME_ID')
        if game_id and game_id not in seen_game_ids:
            seen_game_ids.add(game_id)
            unique_games.append(game_data)
    
    games_data = unique_games
    
    # Filter out games that are already finished if we're collecting for today or future
    # (NBA API sometimes returns finished games for today's date)
    today = date.today()
    if game_date >= today:
        filtered_games = []
        for game_data in games_data:
            status_text = str(game_data.get('GAME_STATUS_TEXT', '')).upper()
            status_id = game_data.get('GAME_STATUS_ID', 0)
            # Only include games that are not finished
            if not ('FINAL' in status_text or status_id == 3):
                filtered_games.append(game_data)
        games_data = filtered_games
        if len(games_data) < len(unique_games):
            print(f"  Filtered out {len(unique_games) - len(games_data)} finished games")
    
    created = 0
    updated = 0
    
    for game_data in games_data:
        try:
            # Extract game info
            game_id = game_data.get('GAME_ID')
            if not game_id:
                continue
            
            # Check if schedule already exists by NBA game ID
            existing = db.query(GameSchedule).filter(
                GameSchedule.nba_game_id == str(game_id)
            ).first()
            
            # Get team IDs
            home_team_id_nba = game_data.get('HOME_TEAM_ID')
            away_team_id_nba = game_data.get('VISITOR_TEAM_ID')
            
            home_team = find_team_by_nba_id(db, home_team_id_nba) if home_team_id_nba else None
            away_team = find_team_by_nba_id(db, away_team_id_nba) if away_team_id_nba else None
            
            if not home_team or not away_team:
                continue  # Skip if we can't find teams
            
            # Get game time
            game_time_str = game_data.get('GAME_DATE_EST')
            game_time = None
            if game_time_str:
                try:
                    game_time = datetime.strptime(game_time_str, '%Y-%m-%dT%H:%M:%S')
                except:
                    try:
                        game_time = datetime.strptime(game_time_str, '%Y-%m-%d')
                    except:
                        pass
            
            # Get status - check multiple fields
            status_text = str(game_data.get('GAME_STATUS_TEXT', '')).upper()
            status_id = game_data.get('GAME_STATUS_ID', 0)
            
            # Status ID meanings: 1=Not Started, 2=In Progress, 3=Finished
            if 'FINAL' in status_text or status_id == 3:
                status = 'finished'
            elif 'LIVE' in status_text or status_id == 2:
                status = 'in_progress'
            else:
                status = 'scheduled'
            
            # If game is marked as finished but date is today or future, it might be a data issue
            # But trust the API status
            
            if existing:
                # Update existing - always update status to match NBA API
                existing.game_time = game_time
                existing.status = status
                # Also update the linked Game record if it exists
                if existing.game_id:
                    game = db.query(Game).filter(Game.game_id == existing.game_id).first()
                    if game:
                        game.game_status = status
                updated += 1
            else:
                # Create new
                schedule = GameSchedule(
                    nba_game_id=str(game_id),  # Store NBA game ID
                    game_date=game_date,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    game_time=game_time,
                    season_id=season.season_id,
                    status=status
                )
                db.add(schedule)
                created += 1
                
        except Exception as e:
            print(f"  ⚠️  Error processing game: {e}")
            continue
    
    return created, updated


def collect_schedules(season_year: str = None, start_date: date = None, end_date: date = None):
    """
    Collect game schedules from NBA API.
    
    Args:
        season_year: Season string (e.g., "2023-24"). If None, uses current season.
        start_date: Start date for collection. If None, uses season start.
        end_date: End date for collection. If None, uses season end or today.
    """
    print("🏀 Collecting NBA Game Schedules...")
    print("=" * 60)
    
    db: Session = SessionLocal()
    client = NBAAPIClient(delay=0.6)
    
    try:
        # Get season
        if season_year:
            season = db.query(Season).filter(Season.season_year == season_year).first()
        else:
            season = db.query(Season).filter(Season.is_current == True).first()
        
        if not season:
            print("❌ No season found. Please seed seasons first.")
            return
        
        print(f"Season: {season.season_year}")
        
        # Determine date range
        if not start_date:
            start_date = season.start_date or date.today()
        if not end_date:
            end_date = min(season.end_date or date.today(), date.today() + timedelta(days=30))
        
        print(f"Date range: {start_date} to {end_date}")
        print("\nCollecting schedules...")
        
        total_created = 0
        total_updated = 0
        current_date = start_date
        
        while current_date <= end_date:
            created, updated = collect_schedule_for_date(db, client, current_date, season)
            total_created += created
            total_updated += updated
            
            if created > 0 or updated > 0:
                print(f"  {current_date}: {created} created, {updated} updated")
            
            db.commit()
            current_date += timedelta(days=1)
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"✅ Created: {total_created} schedules")
        print(f"✅ Updated: {total_updated} schedules")
        
        # Verify
        total = db.query(GameSchedule).filter(
            GameSchedule.season_id == season.season_id
        ).count()
        print(f"\n✅ Total schedules for {season.season_year}: {total}")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error collecting schedules: {e}")
        raise
    finally:
        db.close()


def update_upcoming_schedules(days_ahead: int = 7):
    """
    Update upcoming game schedules (wrapper for update_all.py).
    
    Returns:
        Dict with success status and games_added count
    """
    try:
        today = date.today()
        end_date = today + timedelta(days=days_ahead)
        
        result = collect_schedules(start_date=today, end_date=end_date)
        
        # Count how many schedules were added
        db = SessionLocal()
        try:
            count = db.query(GameSchedule).filter(
                GameSchedule.game_date >= today,
                GameSchedule.game_date <= end_date
            ).count()
        finally:
            db.close()
        
        return {
            'success': True,
            'games_added': count
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Collect NBA game schedules')
    parser.add_argument('--season', type=str, help='Season (e.g., 2023-24)')
    parser.add_argument('--date', type=str, help='Specific date (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=7, help='Number of days ahead to collect')
    
    args = parser.parse_args()
    
    start_date = None
    end_date = None
    
    if args.date:
        start_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        end_date = start_date
    else:
        end_date = date.today() + timedelta(days=args.days)
    
    collect_schedules(season_year=args.season, start_date=start_date, end_date=end_date)
    print("\n✅ Done!")

