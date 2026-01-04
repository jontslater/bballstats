#!/usr/bin/env python3
"""
Manage lineups - confirm starting lineups for games.

Usage:
    # List games without confirmed lineups
    python scripts/manage_lineups.py list
    
    # Confirm lineup for a game
    python scripts/manage_lineups.py confirm --game-id 123 --team LAL --players "LeBron James,Anthony Davis,Russell Westbrook,Kentavious Caldwell-Pope,Dwight Howard"
    
    # Infer lineup from game stats (for completed games)
    python scripts/manage_lineups.py infer --game-id 123
    
    # Show lineup for a game
    python scripts/manage_lineups.py show --game-id 123
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.lineup_service import LineupService
from app.models.player import Player
from app.models.team import Team
from app.models.game import Game

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Manage lineups')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List games without confirmed lineups')
    list_parser.add_argument('--days', type=int, default=1, help='Days ahead to check (default: 1)')
    
    # Confirm command
    confirm_parser = subparsers.add_parser('confirm', help='Confirm a lineup')
    confirm_parser.add_argument('--game-id', type=int, required=True, help='Game ID')
    confirm_parser.add_argument('--team', type=str, required=True, help='Team abbreviation (e.g., LAL)')
    confirm_parser.add_argument('--players', type=str, required=True,
                               help='Comma-separated list of 5 player names')
    confirm_parser.add_argument('--positions', type=str,
                               help='Comma-separated list of positions (PG,SG,SF,PF,C)')
    
    # Infer command
    infer_parser = subparsers.add_parser('infer', help='Infer lineup from game stats')
    infer_parser.add_argument('--game-id', type=int, required=True, help='Game ID')
    
    # Show command
    show_parser = subparsers.add_parser('show', help='Show lineup for a game')
    show_parser.add_argument('--game-id', type=int, required=True, help='Game ID')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    db = SessionLocal()
    try:
        service = LineupService(db)
        
        if args.command == 'list':
            games = service.get_upcoming_games_without_lineups(days_ahead=args.days)
            
            print(f"\n🏀 Games Without Confirmed Lineups (next {args.days} days)")
            print("=" * 60)
            
            if not games:
                print("All games have confirmed lineups!")
            else:
                for game in games:
                    home_team = db.query(Team).filter(Team.team_id == game.home_team_id).first()
                    away_team = db.query(Team).filter(Team.team_id == game.away_team_id).first()
                    
                    home_confirmed = service.is_lineup_confirmed(game.game_id, game.home_team_id)
                    away_confirmed = service.is_lineup_confirmed(game.game_id, game.away_team_id)
                    
                    print(f"\nGame {game.game_id}: {away_team.abbreviation} @ {home_team.abbreviation}")
                    print(f"  Date: {game.game_date}")
                    print(f"  Home lineup: {'✅ Confirmed' if home_confirmed else '❌ Not confirmed'}")
                    print(f"  Away lineup: {'✅ Confirmed' if away_confirmed else '❌ Not confirmed'}")
        
        elif args.command == 'confirm':
            # Get team
            team = db.query(Team).filter(Team.abbreviation == args.team.upper()).first()
            if not team:
                print(f"❌ Team {args.team} not found")
                sys.exit(1)
            
            # Get game
            game = db.query(Game).filter(Game.game_id == args.game_id).first()
            if not game:
                print(f"❌ Game {args.game_id} not found")
                sys.exit(1)
            
            # Parse player names
            player_names = [p.strip() for p in args.players.split(',')]
            if len(player_names) != 5:
                print(f"❌ Must provide exactly 5 players (got {len(player_names)})")
                sys.exit(1)
            
            # Find players
            player_ids = []
            for name in player_names:
                player = db.query(Player).filter(Player.name.ilike(f"%{name}%")).first()
                if not player:
                    print(f"❌ Player '{name}' not found")
                    sys.exit(1)
                player_ids.append(player.player_id)
            
            # Parse positions if provided
            positions = None
            if args.positions:
                positions = [p.strip() for p in args.positions.split(',')]
                if len(positions) != 5:
                    print(f"❌ Must provide exactly 5 positions (got {len(positions)})")
                    sys.exit(1)
            
            # Confirm lineup
            lineups = service.confirm_lineup(
                game_id=args.game_id,
                team_id=team.team_id,
                starter_player_ids=player_ids,
                positions=positions
            )
            
            print(f"✅ Lineup confirmed for {team.name} in game {args.game_id}")
            print(f"   Starters:")
            for lineup in lineups:
                player = db.query(Player).filter(Player.player_id == lineup.player_id).first()
                print(f"     {lineup.position}: {player.name}")
        
        elif args.command == 'infer':
            lineups_by_team = service.infer_lineup_from_game_stats(args.game_id)
            
            if not lineups_by_team:
                print(f"❌ Could not infer lineup for game {args.game_id}")
                sys.exit(1)
            
            game = db.query(Game).filter(Game.game_id == args.game_id).first()
            
            for team_id, lineups in lineups_by_team.items():
                team = db.query(Team).filter(Team.team_id == team_id).first()
                print(f"\n✅ Inferred lineup for {team.name}:")
                for lineup in lineups:
                    player = db.query(Player).filter(Player.player_id == lineup.player_id).first()
                    print(f"   {lineup.position}: {player.name}")
                
                # Save to database
                player_ids = [l.player_id for l in lineups]
                positions = [l.position for l in lineups]
                service.confirm_lineup(
                    game_id=args.game_id,
                    team_id=team_id,
                    starter_player_ids=player_ids,
                    positions=positions
                )
            
            print(f"\n✅ Lineups saved to database")
        
        elif args.command == 'show':
            lineups_by_team = service.get_game_lineups(args.game_id)
            
            game = db.query(Game).filter(Game.game_id == args.game_id).first()
            if not game:
                print(f"❌ Game {args.game_id} not found")
                sys.exit(1)
            
            home_team = db.query(Team).filter(Team.team_id == game.home_team_id).first()
            away_team = db.query(Team).filter(Team.team_id == game.away_team_id).first()
            
            print(f"\n🏀 Lineups for Game {args.game_id}")
            print(f"{away_team.abbreviation} @ {home_team.abbreviation} on {game.game_date}")
            print("=" * 60)
            
            for team_id, lineups in lineups_by_team.items():
                team = db.query(Team).filter(Team.team_id == team_id).first()
                print(f"\n{team.name} ({team.abbreviation}):")
                
                if not lineups:
                    print("  ❌ Lineup not confirmed")
                else:
                    for lineup in sorted(lineups, key=lambda x: x.position or ''):
                        player = db.query(Player).filter(Player.player_id == lineup.player_id).first()
                        print(f"  {lineup.position}: {player.name}")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


