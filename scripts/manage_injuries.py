#!/usr/bin/env python3
"""
Manage injuries - add, update, list injuries.

Usage:
    # List all active injuries
    python scripts/manage_injuries.py list
    
    # List injuries for a team
    python scripts/manage_injuries.py list --team LAL
    
    # Add an injury
    python scripts/manage_injuries.py add --player "LeBron James" --status Out --date 2024-12-20
    
    # Update injury status
    python scripts/manage_injuries.py update --injury-id 1 --status Available
"""
import sys
from pathlib import Path
from datetime import date

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.injury_service import InjuryService
from app.models.player import Player
from app.models.team import Team
from app.models.injury import Injury

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Manage injuries')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List injuries')
    list_parser.add_argument('--team', type=str, help='Team abbreviation (e.g., LAL)')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add an injury')
    add_parser.add_argument('--player', type=str, required=True, help='Player name')
    add_parser.add_argument('--status', type=str, required=True, 
                           choices=['Out', 'Doubtful', 'Questionable', 'Probable', 'Available'],
                           help='Injury status')
    add_parser.add_argument('--date', type=str, required=True, help='Injury date (YYYY-MM-DD)')
    add_parser.add_argument('--type', type=str, help='Injury type (e.g., ankle, knee)')
    add_parser.add_argument('--severity', type=str, choices=['minor', 'moderate', 'severe'],
                           help='Injury severity')
    add_parser.add_argument('--expected-return', type=str, help='Expected return date (YYYY-MM-DD)')
    add_parser.add_argument('--description', type=str, help='Injury description')
    
    # Update command
    update_parser = subparsers.add_parser('update', help='Update an injury')
    update_parser.add_argument('--injury-id', type=int, required=True, help='Injury ID')
    update_parser.add_argument('--status', type=str, 
                              choices=['Out', 'Doubtful', 'Questionable', 'Probable', 'Available'],
                              help='New status')
    update_parser.add_argument('--expected-return', type=str, help='Expected return date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    db = SessionLocal()
    try:
        service = InjuryService(db)
        
        if args.command == 'list':
            if args.team:
                # Get team ID
                team = db.query(Team).filter(Team.abbreviation == args.team.upper()).first()
                if not team:
                    print(f"❌ Team {args.team} not found")
                    sys.exit(1)
                
                injuries = service.get_team_injuries(team.team_id)
                print(f"\n🏥 Active Injuries for {team.name} ({team.abbreviation})")
            else:
                injuries = service.get_active_injuries()
                print("\n🏥 All Active Injuries")
            
            print("=" * 60)
            
            if not injuries:
                print("No active injuries found.")
            else:
                for injury in injuries:
                    player = db.query(Player).filter(Player.player_id == injury.player_id).first()
                    print(f"\n{player.name if player else f'Player {injury.player_id}'}")
                    print(f"  Status: {injury.status}")
                    print(f"  Type: {injury.injury_type or 'N/A'}")
                    print(f"  Date: {injury.injury_date}")
                    if injury.expected_return_date:
                        print(f"  Expected Return: {injury.expected_return_date}")
                    if injury.description:
                        print(f"  Description: {injury.description}")
        
        elif args.command == 'add':
            # Find player
            player = db.query(Player).filter(Player.name.ilike(f"%{args.player}%")).first()
            if not player:
                print(f"❌ Player '{args.player}' not found")
                sys.exit(1)
            
            injury_date = date.fromisoformat(args.date)
            expected_return = date.fromisoformat(args.expected_return) if args.expected_return else None
            
            injury = service.create_or_update_injury(
                player_id=player.player_id,
                status=args.status,
                injury_date=injury_date,
                injury_type=args.type,
                severity=args.severity,
                expected_return_date=expected_return,
                description=args.description,
                source='manual'
            )
            
            print(f"✅ Injury added/updated for {player.name}")
            print(f"   Injury ID: {injury.injury_id}")
            print(f"   Status: {injury.status}")
        
        elif args.command == 'update':
            injury = db.query(Injury).filter(Injury.injury_id == args.injury_id).first()
            if not injury:
                print(f"❌ Injury {args.injury_id} not found")
                sys.exit(1)
            
            if args.status:
                injury.status = args.status
                if args.status == 'Available' and not injury.actual_return_date:
                    injury.actual_return_date = date.today()
            
            if args.expected_return:
                injury.expected_return_date = date.fromisoformat(args.expected_return)
            
            db.commit()
            
            player = db.query(Player).filter(Player.player_id == injury.player_id).first()
            print(f"✅ Injury updated for {player.name if player else f'Player {injury.player_id}'}")
            print(f"   Status: {injury.status}")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

