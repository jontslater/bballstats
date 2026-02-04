#!/usr/bin/env python3
"""
Validate and update player current_team_id based on recent game stats.
Also flags inactive players (no games in last 30 days).

This ensures players are linked to their current teams for prediction generation.
"""
import sys
from pathlib import Path
from datetime import date, timedelta

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from app.database import SessionLocal
from app.models import Player, PlayerGameStat, Game, Team


def validate_and_update_players(sport: str = 'NBA'):
    """Update current_team_id for all players based on their most recent game stats."""
    print(f"🏀 Validating {sport} Players...")
    print("=" * 60)
    
    db: Session = SessionLocal()
    
    try:
        # Get all players for this sport
        players = db.query(Player).filter(Player.sport == sport).all()
        
        updated = 0
        not_found = 0
        inactive = []
        thirty_days_ago = date.today() - timedelta(days=30)
        
        for player in players:
            # Find their most recent game stat
            most_recent_stat = db.query(PlayerGameStat).join(Game).filter(
                and_(
                    PlayerGameStat.player_id == player.player_id,
                    PlayerGameStat.sport == sport
                )
            ).order_by(desc(Game.game_date)).first()
            
            if most_recent_stat and most_recent_stat.team_id:
                # Use the team_id from the most recent game stat
                new_team_id = most_recent_stat.team_id
                
                # Check if player has played in last 30 days
                recent_games_count = db.query(func.count(PlayerGameStat.stat_id)).filter(
                    PlayerGameStat.player_id == player.player_id,
                    PlayerGameStat.sport == sport,
                    PlayerGameStat.game_id.in_(
                        db.query(Game.game_id).filter(Game.game_date >= thirty_days_ago)
                    )
                ).scalar()
                
                if recent_games_count == 0:
                    # Player hasn't played in last 30 days - likely inactive
                    inactive.append({
                        'player': player,
                        'last_game': most_recent_stat.game.game_date if most_recent_stat.game else None,
                        'team_id': new_team_id
                    })
                
                if player.current_team_id != new_team_id:
                    player.current_team_id = new_team_id
                    updated += 1
            else:
                not_found += 1
        
        db.commit()
        
        print(f"\n✅ Updated team assignments: {updated} players")
        print(f"⚠️  No recent games found for: {not_found} players")
        print(f"🚫 Inactive players (no games in 30 days): {len(inactive)}")
        print(f"✅ Total players processed: {len(players)}")
        
        if inactive:
            print("\n📋 Inactive Players:")
            print("-" * 60)
            for item in inactive[:20]:  # Show first 20
                team = db.query(Team).filter(Team.team_id == item['team_id']).first()
                team_name = team.abbreviation if team else "Unknown"
                last_game = item['last_game'].strftime('%Y-%m-%d') if item['last_game'] else "Never"
                print(f"  • {item['player'].name} ({team_name}) - Last game: {last_game}")
            
            if len(inactive) > 20:
                print(f"  ... and {len(inactive) - 20} more")
        
        return {
            'success': True,
            'updated': updated,
            'not_found': not_found,
            'inactive': len(inactive)
        }
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Validate and update player team assignments')
    parser.add_argument('--sport', choices=['NBA', 'NFL'], default='NBA', help='Sport to validate')
    
    args = parser.parse_args()
    validate_and_update_players(sport=args.sport)

