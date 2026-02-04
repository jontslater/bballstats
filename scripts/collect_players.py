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
from app.scrapers.espn_player_scraper import ESPNPlayerScraper


def find_team_by_abbreviation(db: Session, abbreviation: str):
    """Find team by abbreviation."""
    return db.query(Team).filter(Team.abbreviation == abbreviation).first()


def collect_players(season: str = None, is_only_current_season: int = 1, batch_size: int = 50, delay_between_batches: int = 30, use_espn: bool = True):
    """
    Collect players from NBA API and store in database in batches to avoid rate limits.
    
    Args:
        season: Season string (e.g., "2023-24"). If None, uses current season.
        is_only_current_season: 1 for current season only, 0 for all players
        batch_size: Number of players to process before pausing (default: 50)
        delay_between_batches: Seconds to wait between batches (default: 30)
    """
    if use_espn:
        print("🏀 Collecting NBA Players from ESPN (Avoids NBA API Rate Limits)...")
    else:
        print("🏀 Collecting NBA Players (Batched to Minimize Rate Limits)...")
    print("=" * 60)
    
    db: Session = SessionLocal()
    import time
    
    try:
        if use_espn:
            # Use ESPN scraping instead of NBA API
            print("📡 Using ESPN scraping (no rate limits!)")
            print()
            
            scraper = ESPNPlayerScraper(db_session=db, delay=1.5)
            players_data_raw = scraper.get_all_players()
            
            # Convert ESPN format to NBA API-like format for compatibility
            players_data = []
            for p in players_data_raw:
                # We don't have NBA player IDs from ESPN, so we'll use ESPN ID or generate
                # For now, we'll match by name when storing
                players_data.append({
                    'PLAYER_NAME': p['name'],
                    'DISPLAY_FIRST_LAST': p['name'],
                    'TEAM_ABBREVIATION': p['team_abbrev'],
                    'POSITION': p['position'],
                    'HEIGHT': p.get('height'),
                    'WEIGHT': p.get('weight'),
                    'ESPN_ID': p.get('espn_id'),
                    # We'll match by name when storing in DB
                })
        else:
            # Original NBA API approach
            client = NBAAPIClient(delay=2.0)  # Rate limit: 2 seconds between calls (very conservative)
            
            # Wait longer before starting (avoid rate limits from previous calls)
            initial_wait = 20  # Increased to 20 seconds
            print(f"⏳ Waiting {initial_wait} seconds to avoid rate limits...")
            print("   The NBA API has strict rate limits - this wait helps prevent errors.")
            print("   If you've called the API recently, you may need to wait 15-20 minutes.")
            time.sleep(initial_wait)
            
            # Fetch players from API
            print(f"Fetching players from NBA API...")
            print(f"  Season: {season or 'Current'}")
            print(f"  Current season only: {is_only_current_season == 1}")
            print(f"  Batch size: {batch_size} players per batch")
            print(f"  Delay between batches: {delay_between_batches} seconds")
            print("  This will process players in smaller groups to avoid rate limits.")
            print()
            
            # Use more retries for initial player list fetch (this is the most critical call)
            players_data = client.get_all_players(season=season, is_only_current_season=is_only_current_season, max_retries=5)
        
        if not players_data:
            print("\n❌ No players data returned from API")
            print("💡 This might be due to:")
            print("   - NBA API rate limiting (try again in a few minutes)")
            print("   - Network connectivity issues")
            print("   - NBA API endpoint changes")
            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            print("✅ Created: 0 players")
            print("✅ Updated: 0 players")
            print("⚠️  Skipped: 0 players (no data from API)")
            print("\n✅ Total players in database: " + str(db.query(Player).count()))
            return
        
        print(f"✅ Fetched {len(players_data)} players from API")
        print(f"\n📦 Processing in batches of {batch_size} players...")
        print(f"   (Waiting {delay_between_batches}s between batches to avoid rate limits)\n")
        
        # Pre-fetch existing player IDs to skip detailed API calls for existing players
        existing_player_ids = {p.player_id for p in db.query(Player.player_id).filter(Player.sport == 'NBA').all()}
        print(f"📊 Found {len(existing_player_ids)} existing players in database")
        print(f"   (Will skip detailed API calls for existing players to save time/rate limits)\n")
        
        created = 0
        updated = 0
        skipped = 0
        errors = 0
        total_batches = (len(players_data) + batch_size - 1) // batch_size
        
        for batch_num in range(0, len(players_data), batch_size):
            batch = players_data[batch_num:batch_num + batch_size]
            current_batch = (batch_num // batch_size) + 1
            
            print(f"📦 Batch {current_batch}/{total_batches} ({len(batch)} players)...")
            
            for idx_in_batch, player_data in enumerate(batch, 1):
                global_idx = batch_num + idx_in_batch
                
                # Print progress every 10 players or at end of batch
                if global_idx % 10 == 0 or global_idx == len(players_data) or idx_in_batch == len(batch):
                    progress_pct = int((global_idx / len(players_data)) * 100)
                    print(f"[PROGRESS] Processing player {global_idx}/{len(players_data)} ({progress_pct}%)")
                
            try:
                # Extract player info
                name = player_data.get('DISPLAY_FIRST_LAST') or player_data.get('PLAYER_NAME', '')
                if not name:
                    skipped += 1
                    continue
                
                # Get team abbreviation and find team
                team_abbrev = player_data.get('TEAM_ABBREVIATION')
                team = None
                if team_abbrev:
                    team = find_team_by_abbreviation(db, team_abbrev)
                
                # Get position
                position = player_data.get('POSITION', '')
                
                # Get height and weight (already available from ESPN or NBA API)
                height = player_data.get('HEIGHT')
                if isinstance(height, str):
                    # Convert string format "6-8" to inches
                    try:
                        parts = height.split('-')
                        if len(parts) == 2:
                            height = int(parts[0]) * 12 + int(parts[1])
                    except:
                        height = None
                
                weight = player_data.get('WEIGHT')
                if isinstance(weight, str):
                    try:
                        weight = int(weight.replace('lbs', '').strip())
                    except:
                        weight = None
                
                # Try to find existing player by name and team (since ESPN doesn't have NBA player IDs)
                existing_player = None
                if team:
                    # Try exact match first
                    existing_player = db.query(Player).filter(
                        Player.name == name,
                        Player.sport == 'NBA'
                    ).first()
                    
                    if not existing_player:
                        # Try case-insensitive match
                        existing_player = db.query(Player).filter(
                            Player.name.ilike(name),
                            Player.sport == 'NBA'
                        ).first()
                
                # If using NBA API and player doesn't exist, fetch detailed info
                if not use_espn and not existing_player:
                    player_id = player_data.get('PERSON_ID')
                    if player_id and 'client' in locals():
                        # Only fetch detailed info for new players (saves API calls and reduces rate limits)
                        player_info = client.get_player_info(player_id)
                        
                        if player_info:
                            birth_date_str = player_info.get('BIRTHDATE')
                            if birth_date_str:
                                try:
                                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%dT%H:%M:%S').date()
                                except:
                                    try:
                                        birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                                    except:
                                        birth_date = None
                            else:
                                birth_date = None
                        else:
                            birth_date = None
                        
                        # Small delay to avoid overwhelming API (only for new players needing API calls)
                        if idx_in_batch % 5 == 0:
                            time.sleep(0.5)  # Extra delay every 5 new players
                else:
                    birth_date = None
                
                if existing_player:
                    # Update existing player
                    existing_player.name = name
                    existing_player.position = position if position else existing_player.position
                    existing_player.current_team_id = team.team_id if team else existing_player.current_team_id
                    if height:
                        existing_player.height = height
                    if weight:
                        existing_player.weight = weight
                    updated += 1
                else:
                    # Create new player
                    # For ESPN players, we don't have NBA player_id, so we'll generate one or use None
                    # We'll match by name in the future
                    max_player_id = db.query(db.func.max(Player.player_id)).filter(Player.sport == 'NBA').scalar() or 0
                    player_id = max_player_id + 1
                    
                    player = Player(
                        sport='NBA',
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
                    
            except Exception as e:
                    errors += 1
                    print(f"  ⚠️  Error processing player {player_data.get('PERSON_ID', 'unknown')}: {e}")
                    continue
            
            # Commit batch
            db.commit()
            print(f"  ✅ Batch {current_batch}/{total_batches} complete (Created: {created}, Updated: {updated}, Skipped: {skipped})")
            
            # Wait between batches to avoid rate limits (except for last batch)
            if current_batch < total_batches:
                print(f"  ⏳ Waiting {delay_between_batches} seconds before next batch...")
                time.sleep(delay_between_batches)
        
        # Final commit (should already be done, but just in case)
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
    
    parser = argparse.ArgumentParser(description='Collect NBA players in batches to minimize rate limits')
    parser.add_argument('--season', type=str, help='Season (e.g., 2023-24)')
    parser.add_argument('--all-seasons', action='store_true', help='Collect all players, not just current season')
    parser.add_argument('--batch-size', type=int, default=50, help='Number of players per batch (default: 50)')
    parser.add_argument('--batch-delay', type=int, default=30, help='Seconds to wait between batches (default: 30)')
    parser.add_argument('--skip-initial-fetch', action='store_true', help='Skip fetching full player list (use existing players in DB only)')
    parser.add_argument('--extended-wait', action='store_true', help='Wait 10 minutes before starting (for heavily rate-limited scenarios)')
    parser.add_argument('--use-espn', action='store_true', help='Use ESPN scraping instead of NBA API (default: True, avoids rate limits)')
    parser.add_argument('--use-nba-api', action='store_true', help='Use NBA API instead of ESPN (may hit rate limits)')
    
    args = parser.parse_args()
    
    # Determine which method to use: ESPN is default unless --use-nba-api is explicitly set
    # If --use-nba-api is set, use NBA API; otherwise use ESPN (default)
    use_espn = not args.use_nba_api  # ESPN is default unless NBA API is explicitly requested
    
    is_current_only = 0 if args.all_seasons else 1
    
    # If skip initial fetch, we need to provide an empty list
    if args.skip_initial_fetch:
        print("⚠️  --skip-initial-fetch: This will only update existing players in database.")
        print("   No new players will be added. Use this if the API is heavily rate-limited.")
        print()
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            exit(0)
        
        # Just update existing players - we'll modify collect_players to handle this
        db: Session = SessionLocal()
        existing_players = db.query(Player).filter(Player.sport == 'NBA').all()
        print(f"Found {len(existing_players)} existing players to update.")
        print("Note: This mode only updates existing players - it doesn't fetch new ones.")
        print("To add new players, wait for rate limits to reset and run without --skip-initial-fetch")
        db.close()
        exit(0)
    
    # Extended wait for heavily rate-limited scenarios
    if args.extended_wait:
        print("⏳ Extended wait mode: Waiting 10 minutes before starting...")
        print("   This helps when the API has been heavily rate-limited.")
        import time
        for i in range(10, 0, -1):
            print(f"   Starting in {i} minutes...", end='\r')
            time.sleep(60)
        print("   Starting now!                            ")
    
    collect_players(
        season=args.season, 
        is_only_current_season=is_current_only,
        batch_size=args.batch_size,
        delay_between_batches=args.batch_delay,
        use_espn=use_espn
    )
    print("\n✅ Done!")

