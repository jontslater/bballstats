#!/usr/bin/env python3
"""
Generate NFL predictions for upcoming games.

Usage:
    python scripts/generate_nfl_predictions.py [--date DATE] [--game-id GAME_ID]
"""
import sys
import argparse
from pathlib import Path
from datetime import date, datetime, timedelta

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Game, Player, Season, Team, PlayerGameStat
from app.services.prediction_service import PredictionService
from app.config.sport_config import get_sport_config


def generate_predictions_for_game(db: Session, game_id: int, stat_types: list = None):
    """Generate predictions for a specific game."""
    game = db.query(Game).filter(Game.game_id == game_id).first()
    
    if not game:
        print(f"❌ Game {game_id} not found")
        return
    
    if game.sport != 'NFL':
        print(f"❌ Game {game_id} is not an NFL game")
        return
    
    print(f"\n🏈 Generating NFL predictions for Game {game_id}")
    print(f"   {game.away_team.name} @ {game.home_team.name}")
    print(f"   Date: {game.game_date}")
    print("=" * 60)
    
    # Initialize prediction service for NFL
    pred_service = PredictionService(db, sport='NFL')
    
    # Get stat types for NFL if not provided
    if stat_types is None:
        sport_config = get_sport_config('NFL')
        stat_types = sport_config['stat_types']
        # For now, focus on key stats
        stat_types = ['passing_yards', 'rushing_yards', 'receiving_yards', 'receptions']
    
    # Get players who have played for these teams in 2025 season
    # Update their current_team_id based on most recent 2025 stats
    from sqlalchemy import func
    
    players_with_stats = db.query(
        PlayerGameStat.player_id,
        PlayerGameStat.team_id
    ).join(
        Game, PlayerGameStat.game_id == Game.game_id
    ).filter(
        PlayerGameStat.sport == 'NFL',
        Game.season_id == game.season_id,
        PlayerGameStat.team_id.in_([game.home_team_id, game.away_team_id])
    ).distinct().all()
    
    # Update player current_team_id to match their 2025 team
    for player_id, team_id in players_with_stats:
        player = db.query(Player).filter(Player.player_id == player_id).first()
        if player:
            player.current_team_id = team_id
    
    db.commit()
    
    # Get all players from both teams (now with updated teams)
    all_players = db.query(Player).filter(
        Player.sport == 'NFL',
        Player.player_id.in_([p[0] for p in players_with_stats])
    ).all()
    
    print(f"Found {len(all_players)} players with 2025 stats from these teams")
    print(f"Generating predictions for stat types: {', '.join(stat_types)}")
    print()
    
    created = 0
    skipped = 0
    
    for player in all_players:
        # Get position-appropriate stat types
        position_stats = stat_types.copy()
        
        # Filter stats by position (if position is known)
        # For players without position, try all stat types
        if player.position:
            if player.position == 'QB':
                position_stats = [s for s in position_stats if 'passing' in s or 'rushing' in s]
            elif player.position == 'RB':
                position_stats = [s for s in position_stats if 'rushing' in s or 'receiving' in s]
            elif player.position in ['WR', 'TE']:
                position_stats = [s for s in position_stats if 'receiving' in s or 'receptions' in s or 'targets' in s]
            else:
                # Skip other positions for now
                continue
        
        # If no position, try all stat types (will skip ones that don't work)
        if not position_stats:
            continue
        
        for stat_type in position_stats:
            try:
                prediction = pred_service.generate_prediction(
                    player_id=player.player_id,
                    game_id=game_id,
                    stat_type=stat_type
                )
                
                if prediction:
                    # Filter out negative predictions (e.g., passing yards for RBs, rushing yards for QBs)
                    if prediction.safe_line < 0 or prediction.standard_line < 0:
                        skipped += 1
                        continue
                    
                    created += 1
                    print(f"  ✅ {player.name} ({player.position or '?'}) - {stat_type}: {prediction.safe_line:.1f} ({prediction.safe_probability*100:.1f}%)")
                    db.commit()
                else:
                    skipped += 1
                    # Debug: print first few skipped to understand why
                    if skipped <= 3:
                        print(f"  ⏭️  Skipped {player.name} - {stat_type}: No prediction generated (might not meet criteria)")
            except Exception as e:
                import traceback
                print(f"  ⚠️  Error for {player.name} - {stat_type}: {e}")
                traceback.print_exc()
                skipped += 1
    
    print()
    print(f"✅ Created: {created} predictions")
    print(f"⏭️  Skipped: {skipped} predictions")


def generate_predictions_for_date(db: Session, game_date: date):
    """Generate predictions for all games on a date."""
    games = db.query(Game).filter(
        Game.sport == 'NFL',
        Game.game_date == game_date,
        Game.game_status.in_(['scheduled', 'in_progress'])
    ).all()
    
    if not games:
        print(f"No NFL games found for {game_date}")
        return
    
    print(f"🏈 Generating NFL predictions for {game_date}")
    print(f"Found {len(games)} game(s)")
    print("=" * 60)
    
    for game in games:
        generate_predictions_for_game(db, game.game_id)


def main():
    parser = argparse.ArgumentParser(description='Generate NFL predictions')
    parser.add_argument('--date', type=str, help='Date (YYYY-MM-DD)')
    parser.add_argument('--game-id', type=int, help='Specific game ID')
    parser.add_argument('--upcoming', action='store_true', help='Generate for upcoming games')
    
    args = parser.parse_args()
    
    db: Session = SessionLocal()
    
    try:
        if args.game_id:
            generate_predictions_for_game(db, args.game_id)
        elif args.date:
            game_date = datetime.strptime(args.date, '%Y-%m-%d').date()
            generate_predictions_for_date(db, game_date)
        elif args.upcoming:
            # Get upcoming games (next 7 days)
            today = date.today()
            end_date = today + timedelta(days=7)
            games = db.query(Game).filter(
                Game.sport == 'NFL',
                Game.game_date >= today,
                Game.game_date <= end_date,
                Game.game_status == 'scheduled'
            ).all()
            
            print(f"🏈 Generating NFL predictions for upcoming games (next 7 days)")
            print(f"Found {len(games)} game(s)")
            print("=" * 60)
            
            for game in games:
                generate_predictions_for_game(db, game.game_id)
        else:
            print("Please specify --date, --game-id, or --upcoming")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("🏈 NFL Prediction Generator")
    print("=" * 60)
    main()
    print("=" * 60)
    print("✅ Done!")

