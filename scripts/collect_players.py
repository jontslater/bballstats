#!/usr/bin/env python3
"""
Collect and store NBA players from NBA API.

Usage:
    python scripts/collect_players.py
"""
import sys
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Player, Team
from app.scrapers.nba_api_client import NBAAPIClient


def find_team_by_abbreviation(db: Session, abbreviation: str):
    """Find team by abbreviation."""
    return db.query(Team).filter(Team.abbreviation == abbreviation).first()


def collect_players(season: str = None, is_only_current_season: int = 1):
    """
    Collect players from NBA API and store in database.
    
    Args:
        season: Season string (e.g., "2023-24"). If None, uses current season.
        is_only_current_season: 1 for current season only, 0 for all players
    """
    print("🏀 Collecting NBA Players...")
    print("=" * 60)
    
    db: Session = SessionLocal()
    client = NBAAPIClient(delay=1.0)  # Rate limit: 1 second between calls (conservative)
    
    try:
        # Wait a bit before starting (avoid rate limits from previous calls)
        print("⏳ Waiting 5 seconds to avoid rate limits...")
        import time
        time.sleep(5)
        
        # Fetch players from API
        print(f"Fetching players from NBA API...")
        print(f"  Season: {season or 'Current'}")
        print(f"  Current season only: {is_only_current_season == 1}")
        print("  This may take a few minutes due to rate limiting...")
        print("  If this fails, wait 5-10 minutes and try again.")
        print()
        
        players_data = client.get_all_players(season=season, is_only_current_season=is_only_current_season, max_retries=3)
        
        if not players_data:
            print("\n❌ No players data returned from API")
            print("💡 This might be due to:")
            print("   - NBA API rate limiting (try again in a few minutes)")
            print("   - Network connectivity issues")
            print("   - NBA API endpoint changes")
            return
        
        print(f"✅ Fetched {len(players_data)} players from API")
        print("\nProcessing players...")
        
        created = 0
        updated = 0
        skipped = 0
        errors = 0
        
        for idx, player_data in enumerate(players_data, 1):
            try:
                # Extract player info
                player_id = player_data.get('PERSON_ID')
                if not player_id:
                    skipped += 1
                    continue
                
                # Check if player already exists
                existing_player = db.query(Player).filter(Player.player_id == player_id).first()
                
                # Get player name
                name = player_data.get('DISPLAY_FIRST_LAST') or player_data.get('PLAYER_NAME', '')
                
                # Get team abbreviation and find team
                team_abbrev = player_data.get('TEAM_ABBREVIATION')
                team = None
                if team_abbrev:
                    team = find_team_by_abbreviation(db, team_abbrev)
                
                # Get position
                position = player_data.get('POSITION', '')
                
                # Get additional info if available (only for new players to save API calls)
                height = None
                weight = None
                birth_date = None
                
                if not existing_player:
                    # Only fetch detailed info for new players
                    player_info = client.get_player_info(player_id)
                    
                    if player_info:
                        height_str = player_info.get('HEIGHT', '')
                        if height_str:
                            # Convert "6-8" format to inches
                            try:
                                feet, inches = map(int, height_str.split('-'))
                                height = feet * 12 + inches
                            except:
                                pass
                        
                        weight = player_info.get('WEIGHT')
                        if weight:
                            try:
                                weight = int(weight)
                            except:
                                weight = None
                        
                        birth_date_str = player_info.get('BIRTHDATE')
                        if birth_date_str:
                            try:
                                birth_date = datetime.strptime(birth_date_str, '%Y-%m-%dT%H:%M:%S').date()
                            except:
                                try:
                                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                                except:
                                    pass
                
                if existing_player:
                    # Update existing player
                    existing_player.name = name
                    existing_player.position = position if position else existing_player.position
                    existing_player.current_team_id = team.team_id if team else existing_player.current_team_id
                    if height:
                        existing_player.height = height
                    if weight:
                        existing_player.weight = weight
                    if birth_date:
                        existing_player.birth_date = birth_date
                    updated += 1
                else:
                    # Create new player
                    player = Player(
                        player_id=player_id,
                        name=name,
                        position=position if position else None,
                        current_team_id=team.team_id if team else None,
                        height=height,
                        weight=weight,
                        birth_date=birth_date
                    )
                    db.add(player)
                    created += 1
                
                # Progress indicator
                if idx % 25 == 0:
                    print(f"  Processed {idx}/{len(players_data)} players... (Created: {created}, Updated: {updated})")
                    db.commit()  # Commit in batches
                    
                # Small delay to avoid overwhelming API
                if idx % 10 == 0 and not existing_player:
                    time.sleep(0.5)  # Extra delay when fetching player info
                    
            except Exception as e:
                errors += 1
                print(f"  ⚠️  Error processing player {player_data.get('PERSON_ID', 'unknown')}: {e}")
                continue
        
        # Final commit
        db.commit()
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"✅ Created: {created} players")
        print(f"✅ Updated: {updated} players")
        if skipped > 0:
            print(f"⚠️  Skipped: {skipped} players (missing data)")
        if errors > 0:
            print(f"❌ Errors: {errors} players")
        
        # Verify
        total = db.query(Player).count()
        print(f"\n✅ Total players in database: {total}")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error collecting players: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Collect NBA players')
    parser.add_argument('--season', type=str, help='Season (e.g., 2023-24)')
    parser.add_argument('--all-seasons', action='store_true', help='Collect all players, not just current season')
    
    args = parser.parse_args()
    
    is_current_only = 0 if args.all_seasons else 1
    
    collect_players(season=args.season, is_only_current_season=is_current_only)
    print("\n✅ Done!")

