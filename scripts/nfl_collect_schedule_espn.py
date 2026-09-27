#!/usr/bin/env python3
"""
Collect NFL game schedules using ESPN API (primary) with Pro Football Reference fallback.

This script uses ESPN's public API which is more reliable than scraping PFR.
Falls back to PFR scraping only if ESPN fails.

Usage:
    python scripts/nfl_collect_schedule_espn.py [--season SEASON] [--week WEEK]
    python scripts/nfl_collect_schedule_espn.py --all-weeks
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
from app.scrapers.espn_nfl_client import ESPNNFLClient
from app.scrapers.pro_football_reference import ProFootballReferenceScraper


def find_team_by_abbreviation(db: Session, abbrev: str):
    """Find team by abbreviation."""
    return db.query(Team).filter(
        Team.sport == 'NFL',
        Team.abbreviation == abbrev.upper()
    ).first()


def save_games_to_db(db: Session, games: list, season: Season) -> dict:
    """Save games to database."""
    created = 0
    updated = 0
    errors = 0
    
    for game_data in games:
        try:
            home_abbrev = game_data.get('home_team')
            away_abbrev = game_data.get('away_team')
            
            if not home_abbrev or not away_abbrev:
                errors += 1
                continue
            
            home_team = find_team_by_abbreviation(db, home_abbrev)
            away_team = find_team_by_abbreviation(db, away_abbrev)
            
            if not home_team or not away_team:
                print(f"    ⚠️  Could not find teams: {away_abbrev} @ {home_abbrev}")
                errors += 1
                continue
            
            game_date = game_data.get('game_date')
            external_game_id = game_data.get('espn_game_id')  # ESPN ID stored in external_game_id
            status = game_data.get('status', 'scheduled')
            home_score = game_data.get('home_score')
            away_score = game_data.get('away_score')
            
            # Check if schedule already exists
            existing = None
            if external_game_id:
                existing = db.query(GameSchedule).filter(
                    GameSchedule.sport == 'NFL',
                    GameSchedule.external_game_id == external_game_id
                ).first()
            
            if not existing:
                existing = db.query(GameSchedule).filter(
                    GameSchedule.sport == 'NFL',
                    GameSchedule.game_date == game_date,
                    GameSchedule.home_team_id == home_team.team_id,
                    GameSchedule.away_team_id == away_team.team_id
                ).first()
            
            if existing:
                # Update existing
                existing.external_game_id = external_game_id or existing.external_game_id
                existing.status = status
                updated += 1
            else:
                # Create new
                schedule = GameSchedule(
                    sport='NFL',
                    game_date=game_date,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    season_id=season.season_id,
                    external_game_id=external_game_id,  # Use external_game_id for sport-agnostic storage
                    status=status
                )
                db.add(schedule)
                created += 1
            
            # If game is finished, also create/update Game record
            if status == 'finished' and home_score is not None and away_score is not None:
                existing_game = db.query(Game).filter(
                    Game.sport == 'NFL',
                    Game.game_date == game_date,
                    Game.home_team_id == home_team.team_id,
                    Game.away_team_id == away_team.team_id
                ).first()
                
                if existing_game:
                    existing_game.home_score = home_score
                    existing_game.away_score = away_score
                    existing_game.game_status = 'finished'
                else:
                    game = Game(
                        sport='NFL',
                        game_date=game_date,
                        season_id=season.season_id,
                        home_team_id=home_team.team_id,
                        away_team_id=away_team.team_id,
                        home_score=home_score,
                        away_score=away_score,
                        game_status='finished'
                    )
                    db.add(game)
            
        except Exception as e:
            print(f"    ⚠️  Error processing game: {e}")
            errors += 1
            continue
    
    db.commit()
    return {'created': created, 'updated': updated, 'errors': errors}


def collect_week_schedule(db: Session, espn_client: ESPNNFLClient, pfr_scraper: ProFootballReferenceScraper,
                          year: int, week: int, season: Season, use_pfr_fallback: bool = True):
    """Collect schedule for a specific week using ESPN API with PFR fallback."""
    print(f"  Collecting Week {week}, {year}...")
    
    # Try ESPN first
    print(f"    📡 Fetching from ESPN API...")
    games = espn_client.get_games_for_week(year, week)
    
    if not games and use_pfr_fallback:
        print(f"    ⚠️  ESPN failed, falling back to Pro Football Reference...")
        # Fallback to PFR scraping
        # Note: This may still get 403, but we try it as last resort
        url = f"{pfr_scraper.BASE_URL}/years/{year}/week_{week}.htm"
        soup = pfr_scraper._get_page(url)
        
        if soup:
            # Parse PFR format (simplified - focusing on getting basic schedule)
            game_summaries = soup.find_all('div', class_='game_summary')
            games = []
            
            for summary in game_summaries:
                try:
                    team_links = summary.find_all('a', href=lambda x: x and '/teams/' in x)
                    if len(team_links) >= 2:
                        away_abbrev = team_links[0]['href'].split('/')[-2].upper()
                        home_abbrev = team_links[1]['href'].split('/')[-2].upper()
                        
                        # Map PFR abbreviations
                        abbrev_map = {
                            'GNB': 'GB', 'KAN': 'KC', 'NOR': 'NO', 'NWE': 'NE',
                            'RAI': 'LV', 'SFO': 'SF', 'TAM': 'TB'
                        }
                        away_abbrev = abbrev_map.get(away_abbrev, away_abbrev)
                        home_abbrev = abbrev_map.get(home_abbrev, home_abbrev)
                        
                        # Estimate date from week
                        september_start = date(year, 9, 1)
                        days_until_thursday = (3 - september_start.weekday()) % 7
                        first_thursday = september_start + timedelta(days=days_until_thursday)
                        game_date = first_thursday + timedelta(weeks=week - 1)
                        
                        games.append({
                            'home_team': home_abbrev,
                            'away_team': away_abbrev,
                            'game_date': game_date,
                            'status': 'scheduled'
                        })
                except Exception as e:
                    continue
    
    if not games:
        print(f"    ❌ No games found for Week {week}")
        return {'created': 0, 'updated': 0, 'errors': 0}
    
    print(f"    ✅ Found {len(games)} games")
    result = save_games_to_db(db, games, season)
    print(f"    ✅ Week {week}: {result['created']} created, {result['updated']} updated, {result['errors']} errors")
    return result


def collect_season_schedule(db: Session, espn_client: ESPNNFLClient, pfr_scraper: ProFootballReferenceScraper,
                           season_year: str, use_pfr_fallback: bool = True):
    """Collect schedule for entire season."""
    season = db.query(Season).filter(
        Season.sport == 'NFL',
        Season.season_year == season_year
    ).first()
    
    if not season:
        print(f"❌ Season {season_year} not found")
        return
    
    year = int(season_year)
    print(f"\n📅 Collecting NFL schedule for {season_year} season...")
    print(f"Primary source: ESPN API")
    if use_pfr_fallback:
        print(f"Fallback source: Pro Football Reference")
    
    total_created = 0
    total_updated = 0
    total_errors = 0
    
    # NFL: 18 weeks regular + 4 weeks playoffs
    for week in range(1, 23):
        result = collect_week_schedule(db, espn_client, pfr_scraper, year, week, season, use_pfr_fallback)
        total_created += result['created']
        total_updated += result['updated']
        total_errors += result['errors']
    
    print(f"\n✅ Season {season_year} complete:")
    print(f"   Created: {total_created}")
    print(f"   Updated: {total_updated}")
    print(f"   Errors: {total_errors}")


def main():
    parser = argparse.ArgumentParser(description='Collect NFL game schedules using ESPN API')
    parser.add_argument('--season', type=str, help='Season year (e.g., "2024")')
    parser.add_argument('--week', type=int, help='Week number (1-22)')
    parser.add_argument('--all-weeks', action='store_true', help='Collect all weeks for season')
    parser.add_argument('--no-pfr-fallback', action='store_true', help='Disable Pro Football Reference fallback')
    
    args = parser.parse_args()
    
    db: Session = SessionLocal()
    espn_client = ESPNNFLClient(delay=0.5)
    pfr_scraper = ProFootballReferenceScraper(delay=2.0)
    use_pfr_fallback = not args.no_pfr_fallback
    
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
            collect_season_schedule(db, espn_client, pfr_scraper, args.season, use_pfr_fallback)
        elif args.week:
            season = db.query(Season).filter(
                Season.sport == 'NFL',
                Season.season_year == args.season
            ).first()
            if not season:
                print(f"❌ Season {args.season} not found")
                return
            
            year = int(args.season)
            result = collect_week_schedule(db, espn_client, pfr_scraper, year, args.week, season, use_pfr_fallback)
            print(f"\n✅ Week {args.week} complete: {result['created']} created, {result['updated']} updated")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("🏈 Collecting NFL Game Schedules (ESPN API)")
    print("=" * 60)
    main()
    print("=" * 60)
    print("✅ Done!")
