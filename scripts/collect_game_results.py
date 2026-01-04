#!/usr/bin/env python3
"""
Collect game results and box scores from NBA API.

Usage:
    python scripts/collect_game_results.py [--date DATE] [--season SEASON]
    python scripts/collect_game_results.py --previous-day  # Collect yesterday's games
"""
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
import time

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models import (
    Game, Team, Season, Player, PlayerGameStat, GameSchedule
)
from app.scrapers.nba_api_client import NBAAPIClient
from app.scrapers.basketball_reference import BasketballReferenceScraper


def convert_br_to_nba_format(br_box_score: dict, home_team: Team, away_team: Team) -> dict:
    """
    Convert Basketball Reference box score format to NBA API format.
    
    Args:
        br_box_score: Box score from Basketball Reference scraper
        home_team: Home team object
        away_team: Away team object
    
    Returns:
        Dictionary in NBA API format
    """
    player_stats = []
    
    for br_stat in br_box_score.get('player_stats', []):
        # Map Basketball Reference fields to NBA API fields
        nba_stat = {
            'PLAYER_NAME': br_stat.get('PLAYER_NAME', ''),
            'TEAM_ABBREVIATION': br_stat.get('TEAM_ABBREVIATION', ''),
            'MIN': int(br_stat.get('MIN', 0)) if br_stat.get('MIN') else 0,
            'PTS': br_stat.get('PTS', 0),
            'REB': br_stat.get('REB', 0),
            'OREB': br_stat.get('OREB', 0),
            'DREB': br_stat.get('DREB', 0),
            'AST': br_stat.get('AST', 0),
            'STL': br_stat.get('STL', 0),
            'BLK': br_stat.get('BLK', 0),
            'TOV': br_stat.get('TOV', 0),
            'PF': br_stat.get('PF', 0),
            'FGM': br_stat.get('FGM', 0),
            'FGA': br_stat.get('FGA', 0),
            'FG3M': br_stat.get('FG3M', 0),
            'FG3A': br_stat.get('FG3A', 0),
            'FTM': br_stat.get('FTM', 0),
            'FTA': br_stat.get('FTA', 0),
            'PLUS_MINUS': br_stat.get('PLUS_MINUS', 0),
        }
        player_stats.append(nba_stat)
    
    return {
        'player_stats': player_stats,
        'team_stats': []  # We don't need team stats for now
    }


def find_team_by_nba_id(db: Session, nba_team_id: int):
    """Find team by NBA API team ID using abbreviation mapping."""
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


def get_or_create_player(db: Session, nba_player_id: int, player_name: str):
    """Get existing player or create a new one."""
    player = db.query(Player).filter(Player.player_id == nba_player_id).first()
    
    if not player:
        # Create new player (we'll update details later)
        player = Player(
            player_id=nba_player_id,
            name=player_name
        )
        db.add(player)
        db.flush()  # Flush to get the ID
    
    return player


def collect_game_for_date(db: Session, client: NBAAPIClient, game_date: date, season: Season):
    """Collect all games for a specific date."""
    print(f"\nCollecting games for {game_date}...")
    
    games_data = client.get_game_schedule(game_date)
    
    if not games_data:
        print(f"  No games scheduled for {game_date}")
        return 0, 0
    
    total_games = len(games_data)
    games_processed = 0
    games_created = 0
    
    print(f"  Found {total_games} games to process")
    
    for idx, game_data in enumerate(games_data, 1):
        print(f"  Processing game {idx}/{total_games}...")
        try:
            nba_game_id = game_data.get('GAME_ID')
            if not nba_game_id:
                continue
            
            # Check if game already exists
            existing_game = db.query(Game).filter(
                and_(
                    Game.game_date == game_date,
                    Game.home_team_id == find_team_by_nba_id(db, game_data.get('HOME_TEAM_ID')).team_id if game_data.get('HOME_TEAM_ID') else None,
                    Game.away_team_id == find_team_by_nba_id(db, game_data.get('VISITOR_TEAM_ID')).team_id if game_data.get('VISITOR_TEAM_ID') else None
                )
            ).first()
            
            # Get team IDs
            home_team = find_team_by_nba_id(db, game_data.get('HOME_TEAM_ID'))
            away_team = find_team_by_nba_id(db, game_data.get('VISITOR_TEAM_ID'))
            
            if not home_team or not away_team:
                print(f"  ⚠️  Skipping game {nba_game_id} - teams not found")
                continue
            
            # Check game status - only process finished games
            game_status_id = game_data.get('GAME_STATUS_ID', 1)
            game_status_text = game_data.get('GAME_STATUS_TEXT', '')
            
            if game_status_id == 1:  # Not started
                print(f"  ⏸️  Game {nba_game_id} not started yet ({game_status_text})")
                continue
            elif game_status_id == 2:  # In progress
                print(f"  ⏳ Game {nba_game_id} in progress - will collect when finished")
                continue
            elif game_status_id != 3:  # Not finished
                print(f"  ⚠️  Game {nba_game_id} status unknown ({game_status_id})")
                continue
            
            # Game is finished (status = 3), get box score
            print(f"  📊 Fetching box score for finished game {nba_game_id}...")
            time.sleep(1)  # Rate limit
            box_score = client.get_game_box_score(str(nba_game_id))
            
            # If NBA API fails, try Basketball Reference as fallback
            if not box_score or not box_score.get('player_stats'):
                print(f"  ⚠️  NBA API failed, trying Basketball Reference...")
                br_scraper = BasketballReferenceScraper()
                br_box_score = br_scraper.get_box_score_by_date_and_teams(game_date, home_team.abbreviation)
                
                if br_box_score and br_box_score.get('player_stats'):
                    print(f"  ✅ Got box score from Basketball Reference!")
                    # Convert Basketball Reference format to NBA API format
                    box_score = convert_br_to_nba_format(br_box_score, home_team, away_team)
                    # Update scores from Basketball Reference if available
                    if br_box_score.get('home_score') is not None:
                        home_score = br_box_score.get('home_score')
                    if br_box_score.get('visitor_score') is not None:
                        away_score = br_box_score.get('visitor_score')
                else:
                    print(f"  ⚠️  Basketball Reference also failed for game {nba_game_id}")
                    continue
            
            # Debug: Check what we got
            player_stats_data = box_score.get('player_stats', [])
            if not player_stats_data:
                print(f"  ⚠️  Box score returned but no player stats (game may not have been played)")
                # Still create the game record, just without player stats
                continue
            
            # Create or update game (scores may have been updated from Basketball Reference)
            if 'home_score' not in locals():
                home_score = game_data.get('HOME_TEAM_SCORE')
            if 'away_score' not in locals():
                away_score = game_data.get('VISITOR_TEAM_SCORE')
            
            if existing_game:
                game = existing_game
                game.home_score = home_score
                game.away_score = away_score
                game.game_status = "finished"
            else:
                game = Game(
                    game_date=game_date,
                    season_id=season.season_id,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    home_score=home_score,
                    away_score=away_score,
                    game_status="finished"
                )
                db.add(game)
                db.flush()  # Get game_id
                games_created += 1
            
            # Process player stats
            player_stats_data = box_score.get('player_stats', [])
            stats_created = 0
            
            for stat_data in player_stats_data:
                try:
                    player_name = stat_data.get('PLAYER_NAME', 'Unknown')
                    if not player_name or player_name == 'Unknown':
                        continue
                    
                    # Try to get player ID first (NBA API format)
                    nba_player_id = stat_data.get('PLAYER_ID')
                    
                    if nba_player_id:
                        # NBA API format - use player ID
                        player = get_or_create_player(db, nba_player_id, player_name)
                    else:
                        # Basketball Reference format - find by name and team
                        team_abbrev = stat_data.get('TEAM_ABBREVIATION')
                        team = db.query(Team).filter(Team.abbreviation == team_abbrev).first() if team_abbrev else None
                        
                        # Try to find player by name (exact match)
                        player = db.query(Player).filter(Player.name == player_name).first()
                        
                        if not player:
                            # If not found, we'll skip for now (could add fuzzy matching later)
                            print(f"    ⚠️  Player not found in database: {player_name} ({team_abbrev})")
                            continue
                    
                    # Check if stat already exists
                    existing_stat = db.query(PlayerGameStat).filter(
                        and_(
                            PlayerGameStat.player_id == player.player_id,
                            PlayerGameStat.game_id == game.game_id
                        )
                    ).first()
                    
                    if existing_stat:
                        continue  # Skip if already exists
                    
                    # Get team (player's team for this game)
                    team_abbrev = stat_data.get('TEAM_ABBREVIATION')
                    team = db.query(Team).filter(Team.abbreviation == team_abbrev).first() if team_abbrev else None
                    
                    # Determine opponent
                    opponent_team_id = away_team.team_id if team == home_team else home_team.team_id
                    
                    # Helper function to safely convert to int (handles NaN, None, etc.)
                    def safe_int(value, default=0):
                        try:
                            if value is None or (isinstance(value, float) and (value != value)):  # NaN check
                                return default
                            return int(float(value))
                        except (ValueError, TypeError):
                            return default
                    
                    # Extract stats
                    minutes_value = stat_data.get('MIN', 0)
                    minutes_played = 0
                    if isinstance(minutes_value, str) and ':' in minutes_value:
                        # Format: "24:30"
                        try:
                            mins, secs = map(int, minutes_value.split(':'))
                            minutes_played = mins + (secs / 60)
                        except:
                            minutes_played = 0
                    elif isinstance(minutes_value, (int, float)):
                        # Already in decimal format (from Basketball Reference conversion)
                        minutes_played = float(minutes_value)
                    else:
                        minutes_played = 0
                    
                    # Create player game stat
                    player_stat = PlayerGameStat(
                        player_id=player.player_id,
                        game_id=game.game_id,
                        team_id=team.team_id if team else None,
                        opponent_team_id=opponent_team_id,
                        minutes_played=int(minutes_played),
                        points=safe_int(stat_data.get('PTS')),
                        rebounds=safe_int(stat_data.get('REB')),
                        offensive_rebounds=safe_int(stat_data.get('OREB')),
                        defensive_rebounds=safe_int(stat_data.get('DREB')),
                        assists=safe_int(stat_data.get('AST')),
                        steals=safe_int(stat_data.get('STL')),
                        blocks=safe_int(stat_data.get('BLK')),
                        turnovers=safe_int(stat_data.get('TOV') or stat_data.get('TO')),
                        personal_fouls=safe_int(stat_data.get('PF')),
                        field_goals_made=safe_int(stat_data.get('FGM')),
                        field_goals_attempted=safe_int(stat_data.get('FGA')),
                        three_pointers_made=safe_int(stat_data.get('FG3M')),
                        three_pointers_attempted=safe_int(stat_data.get('FG3A')),
                        free_throws_made=safe_int(stat_data.get('FTM')),
                        free_throws_attempted=safe_int(stat_data.get('FTA')),
                        plus_minus=safe_int(stat_data.get('PLUS_MINUS')),
                        is_home=(team == home_team)
                    )
                    db.add(player_stat)
                    stats_created += 1
                    
                except Exception as e:
                    print(f"    ⚠️  Error processing player stat: {e}")
                    continue
            
            games_processed += 1
            print(f"    ✅ Game {nba_game_id}: {stats_created} player stats added")
            
            # Commit after each game (with error handling)
            try:
                db.commit()
                print(f"    💾 Committed game {nba_game_id} to database")
            except Exception as commit_error:
                print(f"    ⚠️  Commit error for game {nba_game_id}: {commit_error}")
                db.rollback()
                raise  # Re-raise to be caught by outer exception handler
            
        except Exception as e:
            print(f"  ❌ Error processing game {nba_game_id if 'nba_game_id' in locals() else 'unknown'}: {e}")
            import traceback
            print(f"  Traceback: {traceback.format_exc()}")
            try:
                db.rollback()
            except:
                pass  # Ignore rollback errors
            continue
    
    print(f"\n  ✅ Completed processing {games_processed}/{total_games} games")
    
    return games_processed, games_created


def collect_previous_day_games(target_date: date = None):
    """Collect previous day's game results."""
    if not target_date:
        target_date = date.today() - timedelta(days=1)
    
    print("🏀 Collecting Previous Day's Game Results...")
    print("=" * 60)
    print(f"Date: {target_date}")
    
    db: Session = SessionLocal()
    client = NBAAPIClient(delay=1.0)
    
    try:
        # Get current season
        season = db.query(Season).filter(Season.is_current == True).first()
        if not season:
            print("❌ No current season found. Please seed seasons first.")
            return
        
        games_processed, games_created = collect_game_for_date(db, client, target_date, season)
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"✅ Games processed: {games_processed}")
        print(f"✅ Games created: {games_created}")
        
        # Count total games and player stats
        total_games = db.query(Game).filter(Game.game_date == target_date).count()
        total_stats = db.query(PlayerGameStat).join(Game).filter(
            Game.game_date == target_date
        ).count()
        
        print(f"✅ Total games in database for {target_date}: {total_games}")
        print(f"✅ Total player stats for {target_date}: {total_stats}")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error collecting game results: {e}")
        raise
    finally:
        db.close()


def collect_season_games(season_year: str, start_date: date = None, end_date: date = None):
    """Collect all games for a season or date range."""
    print("🏀 Collecting Season Game Results...")
    print("=" * 60)
    
    db: Session = SessionLocal()
    client = NBAAPIClient(delay=1.0)
    
    try:
        season = db.query(Season).filter(Season.season_year == season_year).first()
        if not season:
            print(f"❌ Season {season_year} not found")
            return
        
        if not start_date:
            start_date = season.start_date or date.today() - timedelta(days=30)
        if not end_date:
            end_date = min(season.end_date or date.today(), date.today())
        
        print(f"Season: {season_year}")
        print(f"Date range: {start_date} to {end_date}")
        print("\nThis will take a while due to rate limiting...")
        print("Processing one game at a time...\n")
        
        total_games = 0
        total_created = 0
        current_date = start_date
        
        while current_date <= end_date:
            games_processed, games_created = collect_game_for_date(db, client, current_date, season)
            total_games += games_processed
            total_created += games_created
            
            current_date += timedelta(days=1)
            
            # Small delay between days
            if current_date <= end_date:
                time.sleep(2)
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"✅ Total games processed: {total_games}")
        print(f"✅ Total games created: {total_created}")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Collect NBA game results')
    parser.add_argument('--date', type=str, help='Specific date (YYYY-MM-DD)')
    parser.add_argument('--previous-day', action='store_true', help='Collect yesterday\'s games')
    parser.add_argument('--season', type=str, help='Season (e.g., 2023-24)')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    if args.previous_day:
        collect_previous_day_games()
    elif args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        collect_previous_day_games(target_date)
    elif args.season:
        start_date = None
        end_date = None
        if args.start_date:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        if args.end_date:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        collect_season_games(args.season, start_date, end_date)
    else:
        # Default: collect previous day
        collect_previous_day_games()
    
    print("\n✅ Done!")

