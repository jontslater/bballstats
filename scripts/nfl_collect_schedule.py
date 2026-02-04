#!/usr/bin/env python3
"""
Collect and store NFL game schedules from Pro Football Reference.

Usage:
    python scripts/nfl_collect_schedule.py [--season SEASON] [--week WEEK]
    python scripts/nfl_collect_schedule.py --all-weeks  # Collect all weeks for current season
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime, date, timedelta

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models import GameSchedule, Team, Season, Game
from app.scrapers.pro_football_reference import ProFootballReferenceScraper


def find_team_by_pfr_abbreviation(db: Session, pfr_abbrev: str):
    """
    Find team by Pro Football Reference abbreviation.
    
    PFR uses some different abbreviations (e.g., GNB for GB, KAN for KC)
    """
    # Map PFR abbreviations to our abbreviations
    # PFR uses historical/alternative abbreviations
    abbrev_map = {
        'GNB': 'GB',   # Green Bay
        'KAN': 'KC',   # Kansas City
        'NOR': 'NO',   # New Orleans
        'NWE': 'NE',   # New England
        'RAI': 'LV',   # Las Vegas Raiders
        'SFO': 'SF',   # San Francisco
        'TAM': 'TB',   # Tampa Bay
        # Additional PFR abbreviations discovered
        'RAV': 'BAL',  # Baltimore Ravens
        'CRD': 'ARI',  # Arizona Cardinals
        'OTI': 'TEN',  # Tennessee Titans (Oilers/Titans)
        'HTX': 'HOU',  # Houston Texans
        'CLT': 'IND',  # Indianapolis Colts
        'SDG': 'LAC',  # Los Angeles Chargers (San Diego)
        'RAM': 'LAR',  # Los Angeles Rams
        'CRD': 'ARI',  # Arizona Cardinals
    }
    
    # Convert to our abbreviation
    our_abbrev = abbrev_map.get(pfr_abbrev.upper(), pfr_abbrev.upper())
    
    return db.query(Team).filter(
        Team.sport == 'NFL',
        Team.abbreviation == our_abbrev
    ).first()


def collect_week_schedule(db: Session, scraper: ProFootballReferenceScraper, year: int, week: int, season: Season):
    """Collect schedule for a specific week."""
    print(f"  Collecting Week {week}, {year}...")
    
    # Pro Football Reference URL format: /years/{year}/week_{week}.htm
    url = f"{scraper.BASE_URL}/years/{year}/week_{week}.htm"
    soup = scraper._get_page(url)
    
    if not soup:
        print(f"    ⚠️  Could not fetch week {week} schedule")
        return {'created': 0, 'updated': 0, 'errors': 0}
    
    created = 0
    updated = 0
    errors = 0
    
    # Find game rows - PFR has tables with game info
    # Look for divs with class "game_summary" or table rows
    game_summaries = soup.find_all('div', class_='game_summary')
    
    if not game_summaries:
        # Try alternative structure - look for game links
        game_links = soup.find_all('a', href=lambda x: x and '/boxscores/' in x and year in x)
        game_summaries = []
        for link in game_links:
            # Extract game info from link
            href = link['href']
            game_id = href.split('/')[-1].replace('.htm', '')
            # Try to get parent container
            parent = link.find_parent(['div', 'td', 'tr'])
            if parent:
                game_summaries.append(parent)
    
    for game_summary in game_summaries:
        try:
            # Try to extract game info
            # PFR format varies, try multiple approaches
            
            # Method 1: Look for team links
            team_links = game_summary.find_all('a', href=lambda x: x and '/teams/' in x)
            if len(team_links) < 2:
                continue
            
            # Get away and home team abbreviations from links
            away_link = team_links[0]['href']
            home_link = team_links[1]['href']
            
            away_pfr_abbrev = away_link.split('/')[-2].upper()
            home_pfr_abbrev = home_link.split('/')[-2].upper()
            
            away_team = find_team_by_pfr_abbreviation(db, away_pfr_abbrev)
            home_team = find_team_by_pfr_abbreviation(db, home_pfr_abbrev)
            
            if not away_team or not home_team:
                errors += 1
                print(f"    ⚠️  Could not find teams: {away_pfr_abbrev} @ {home_pfr_abbrev}")
                continue
            
            # Get game date - try to find it in the summary
            game_date = None
            date_elem = game_summary.find(['time', 'span'], class_=['date', 'game-time'])
            if date_elem:
                try:
                    date_str = date_elem.get('datetime') or date_elem.text
                    game_date = datetime.strptime(date_str.split()[0], '%Y-%m-%d').date()
                except:
                    pass
            
            # If we can't find date, estimate from week
            if not game_date:
                # NFL weeks: Week 1 typically starts first Thursday in September
                # For simplicity, calculate based on week number
                # Week 1 = first Thursday of September
                september_start = date(year, 9, 1)
                # Find first Thursday
                days_until_thursday = (3 - september_start.weekday()) % 7
                first_thursday = september_start + timedelta(days=days_until_thursday)
                # Week 1 Thursday + (week - 1) * 7 days
                game_date = first_thursday + timedelta(weeks=week - 1)
            
            # Get game time if available
            game_time = None
            time_elem = game_summary.find(['time', 'span'], class_=['time', 'game-time'])
            if time_elem:
                try:
                    time_str = time_elem.get('datetime') or time_elem.text
                    # Try to parse time
                    if 'T' in time_str:
                        game_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                except:
                    pass
            
            # Get game ID from box score link
            box_score_link = game_summary.find('a', href=lambda x: x and '/boxscores/' in x)
            nfl_game_id = None
            if box_score_link:
                nfl_game_id = box_score_link['href'].split('/')[-1].replace('.htm', '')
            
            # Check if schedule already exists
            existing = None
            if nfl_game_id:
                existing = db.query(GameSchedule).filter(
                    GameSchedule.sport == 'NFL',
                    GameSchedule.nba_game_id == nfl_game_id
                ).first()
            
            if not existing:
                # Also check by teams and date
                existing = db.query(GameSchedule).filter(
                    GameSchedule.sport == 'NFL',
                    GameSchedule.game_date == game_date,
                    GameSchedule.home_team_id == home_team.team_id,
                    GameSchedule.away_team_id == away_team.team_id
                ).first()
            
            if existing:
                # Update existing
                existing.game_time = game_time
                existing.nba_game_id = nfl_game_id or existing.nba_game_id
                updated += 1
            else:
                # Create new
                schedule = GameSchedule(
                    sport='NFL',
                    game_date=game_date,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    game_time=game_time,
                    season_id=season.season_id,
                    nba_game_id=nfl_game_id,
                    status='scheduled'
                )
                db.add(schedule)
                created += 1
                
        except Exception as e:
            errors += 1
            print(f"    ⚠️  Error processing game: {e}")
            continue
    
    db.commit()
    print(f"    ✅ Week {week}: {created} created, {updated} updated, {errors} errors")
    return {'created': created, 'updated': updated, 'errors': errors}


def collect_season_schedule(db: Session, scraper: ProFootballReferenceScraper, season_year: str):
    """Collect schedule for entire season (all 18 weeks)."""
    season = db.query(Season).filter(
        Season.sport == 'NFL',
        Season.season_year == season_year
    ).first()
    
    if not season:
        print(f"❌ Season {season_year} not found")
        return
    
    year = int(season_year)
    print(f"\n📅 Collecting NFL schedule for {season_year} season...")
    
    total_created = 0
    total_updated = 0
    total_errors = 0
    
    # NFL regular season: 18 weeks (2021+)
    # Plus playoffs weeks 19-22
    for week in range(1, 23):  # Weeks 1-22 (regular + playoffs)
        result = collect_week_schedule(db, scraper, year, week, season)
        total_created += result['created']
        total_updated += result['updated']
        total_errors += result['errors']
        
        # Small delay between weeks
        import time
        time.sleep(1)
    
    print(f"\n✅ Season {season_year} complete:")
    print(f"   Created: {total_created}")
    print(f"   Updated: {total_updated}")
    print(f"   Errors: {total_errors}")


def main():
    parser = argparse.ArgumentParser(description='Collect NFL game schedules')
    parser.add_argument('--season', type=str, help='Season year (e.g., "2024")')
    parser.add_argument('--week', type=int, help='Week number (1-22)')
    parser.add_argument('--all-weeks', action='store_true', help='Collect all weeks for season')
    
    args = parser.parse_args()
    
    db: Session = SessionLocal()
    scraper = ProFootballReferenceScraper(delay=2.0)
    
    try:
        # Default to current season
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
            collect_season_schedule(db, scraper, args.season)
        elif args.week:
            season = db.query(Season).filter(
                Season.sport == 'NFL',
                Season.season_year == args.season
            ).first()
            if not season:
                print(f"❌ Season {args.season} not found")
                return
            
            year = int(args.season)
            collect_week_schedule(db, scraper, year, args.week, season)
            print(f"\n✅ Week {args.week} collection complete")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("🏈 Collecting NFL Game Schedules...")
    print("=" * 60)
    main()
    print("=" * 60)
    print("✅ Done!")

