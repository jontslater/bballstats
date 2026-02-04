#!/usr/bin/env python3
"""
Collect NFL game results and box scores from Pro Football Reference.

Usage:
    python scripts/nfl_collect_game_results.py [--date DATE] [--season SEASON]
    python scripts/nfl_collect_game_results.py --previous-day  # Collect yesterday's games
"""
import sys
import argparse
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
from app.scrapers.pro_football_reference import ProFootballReferenceScraper


def find_team_by_pfr_abbreviation(db: Session, pfr_abbrev: str):
    """Find team by Pro Football Reference abbreviation."""
    abbrev_map = {
        'GNB': 'GB', 'KAN': 'KC', 'NOR': 'NO', 'NWE': 'NE',
        'RAI': 'LV', 'SFO': 'SF', 'TAM': 'TB',
        # Additional PFR abbreviations
        'RAV': 'BAL', 'CRD': 'ARI', 'OTI': 'TEN', 'HTX': 'HOU',
        'CLT': 'IND', 'SDG': 'LAC', 'RAM': 'LAR'
    }
    our_abbrev = abbrev_map.get(pfr_abbrev.upper(), pfr_abbrev.upper())
    return db.query(Team).filter(
        Team.sport == 'NFL',
        Team.abbreviation == our_abbrev
    ).first()


def get_or_create_nfl_player(db: Session, player_name: str, team: Team, position: str = None):
    """Get or create NFL player by name and team."""
    # Try to find existing player by name and team
    player = db.query(Player).filter(
        Player.sport == 'NFL',
        Player.name == player_name,
        Player.current_team_id == team.team_id
    ).first()
    
    if not player:
        # Try just by name
        player = db.query(Player).filter(
            Player.sport == 'NFL',
            Player.name == player_name
        ).first()
    
    if not player:
        # Create new player
        # We don't have player IDs from PFR, so we'll use a hash or auto-increment
        # For now, let's use name-based lookup
        player = Player(
            sport='NFL',
            name=player_name,
            position=position,
            current_team_id=team.team_id
        )
        db.add(player)
        db.flush()  # Get player_id
    
    return player


def collect_game_for_date(db: Session, scraper: ProFootballReferenceScraper, game_date: date, season: Season):
    """Collect all NFL games for a specific date."""
    print(f"\nCollecting NFL games for {game_date}...")
    
    games_data = scraper.get_games_for_date(game_date)
    
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
            game_id = game_data.get('game_id')
            away_pfr = game_data.get('away_team')
            home_pfr = game_data.get('home_team')
            
            if not away_pfr or not home_pfr:
                print(f"    ⚠️  Missing team info, skipping")
                continue
            
            away_team = find_team_by_pfr_abbreviation(db, away_pfr)
            home_team = find_team_by_pfr_abbreviation(db, home_pfr)
            
            if not away_team or not home_team:
                print(f"    ⚠️  Could not find teams: {away_pfr} @ {home_pfr}")
                continue
            
            # Check if game already exists
            existing_game = db.query(Game).filter(
                and_(
                    Game.sport == 'NFL',
                    Game.game_date == game_date,
                    Game.home_team_id == home_team.team_id,
                    Game.away_team_id == away_team.team_id
                )
            ).first()
            
            # Check if game is finished (has scores)
            away_score = game_data.get('away_score')
            home_score = game_data.get('home_score')
            
            if away_score is None or home_score is None:
                print(f"    ⏸️  Game not finished yet (no scores)")
                # Still create game record as scheduled
                if not existing_game:
                    game = Game(
                        sport='NFL',
                        game_date=game_date,
                        season_id=season.season_id,
                        home_team_id=home_team.team_id,
                        away_team_id=away_team.team_id,
                        game_status='scheduled'
                    )
                    db.add(game)
                    db.flush()
                    games_created += 1
                continue
            
            # Game is finished, get box score
            if not game_id:
                # Generate game_id from date and teams
                game_id = f"{game_date.strftime('%Y%m%d')}{home_pfr.lower()}"
            
            print(f"    📊 Fetching box score...")
            time.sleep(2)  # Rate limit for PFR
            box_score = scraper.get_box_score(game_id, game_date)
            
            if not box_score:
                print(f"    ⚠️  Could not get box score")
                # Still create game record with scores
                if not existing_game:
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
                    games_created += 1
                continue
            
            # Update scores from box score if available
            if box_score.get('home_score'):
                home_score = box_score['home_score']
            if box_score.get('away_score'):
                away_score = box_score['away_score']
            
            # Create or update game
            if existing_game:
                game = existing_game
                game.home_score = home_score
                game.away_score = away_score
                game.game_status = 'finished'
                game.sport = 'NFL'  # Ensure sport is set
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
                db.flush()  # Get game_id
                games_created += 1
            
            # Process player stats
            player_stats_data = box_score.get('player_stats', [])
            if not player_stats_data:
                print(f"    ⚠️  No player stats in box score")
                db.commit()
                games_processed += 1
                continue
            
            stats_created = 0
            stats_updated = 0
            
            for stat_data in player_stats_data:
                try:
                    player_name = stat_data.get('player_name')
                    if not player_name:
                        continue
                    
                    team_abbrev = stat_data.get('team_abbreviation')
                    if not team_abbrev:
                        continue
                    
                    # Find team
                    team = find_team_by_pfr_abbreviation(db, team_abbrev)
                    if not team:
                        continue
                    
                    # Determine opponent
                    opponent_team = away_team if team.team_id == home_team.team_id else home_team
                    
                    # Get or create player
                    position = stat_data.get('position')
                    player = get_or_create_nfl_player(db, player_name, team, position)
                    
                    # Check if stat already exists
                    existing_stat = db.query(PlayerGameStat).filter(
                        PlayerGameStat.sport == 'NFL',
                        PlayerGameStat.player_id == player.player_id,
                        PlayerGameStat.game_id == game.game_id
                    ).first()
                    
                    if existing_stat:
                        stat = existing_stat
                        stats_updated += 1
                    else:
                        stat = PlayerGameStat(
                            sport='NFL',
                            player_id=player.player_id,
                            game_id=game.game_id,
                            team_id=team.team_id,
                            opponent_team_id=opponent_team.team_id,
                            is_home=(team.team_id == home_team.team_id)
                        )
                        db.add(stat)
                        stats_created += 1
                    
                    # Update NFL stats
                    stat.passing_yards = stat_data.get('passing_yards')
                    stat.passing_tds = stat_data.get('passing_tds')
                    stat.interceptions = stat_data.get('interceptions')
                    stat.completions = stat_data.get('passing_completions') or stat_data.get('completions')
                    stat.pass_attempts = stat_data.get('passing_attempts') or stat_data.get('attempts')
                    
                    stat.rushing_yards = stat_data.get('rushing_yards')
                    stat.rushing_tds = stat_data.get('rushing_tds')
                    stat.rushing_attempts = stat_data.get('rushing_attempts')
                    
                    stat.receptions = stat_data.get('receptions')
                    stat.receiving_yards = stat_data.get('receiving_yards')
                    stat.receiving_tds = stat_data.get('receiving_tds')
                    stat.targets = stat_data.get('targets')
                    
                    stat.fumbles = stat_data.get('fumbles')
                    stat.fumbles_lost = stat_data.get('fumbles_lost')
                    
                    # Flush to catch constraint errors early
                    db.flush()
                    
                except Exception as e:
                    # Rollback to clear the failed transaction
                    db.rollback()
                    # Re-fetch game to maintain reference
                    game = db.query(Game).filter(Game.game_id == game.game_id).first()
                    print(f"      ⚠️  Error processing player {player_name}: {str(e)[:50]}")
                    continue
            
            db.commit()
            print(f"    ✅ Game saved: {stats_created} stats created, {stats_updated} updated")
            games_processed += 1
            
        except Exception as e:
            db.rollback()
            print(f"    ❌ Error processing game: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    return games_created, games_processed


def main():
    parser = argparse.ArgumentParser(description='Collect NFL game results')
    parser.add_argument('--date', type=str, help='Date (YYYY-MM-DD)')
    parser.add_argument('--season', type=str, help='Season year (e.g., "2024")')
    parser.add_argument('--previous-day', action='store_true', help='Collect yesterday\'s games')
    
    args = parser.parse_args()
    
    db: Session = SessionLocal()
    scraper = ProFootballReferenceScraper(delay=2.0)
    
    try:
        # Determine date
        if args.previous_day:
            game_date = date.today() - timedelta(days=1)
        elif args.date:
            game_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        else:
            game_date = date.today()
        
        # Get season
        if args.season:
            season = db.query(Season).filter(
                Season.sport == 'NFL',
                Season.season_year == args.season
            ).first()
        else:
            # Find season that contains this date
            season = db.query(Season).filter(
                Season.sport == 'NFL',
                Season.start_date <= game_date,
                Season.end_date >= game_date
            ).first()
        
        if not season:
            print(f"❌ No NFL season found for date {game_date}")
            return
        
        print(f"📅 Collecting games for {game_date} (Season: {season.season_year})")
        
        games_created, games_processed = collect_game_for_date(db, scraper, game_date, season)
        
        print(f"\n✅ Complete: {games_created} games created, {games_processed} games processed")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("🏈 Collecting NFL Game Results...")
    print("=" * 60)
    main()
    print("=" * 60)
    print("✅ Done!")

