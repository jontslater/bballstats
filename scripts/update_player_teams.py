#!/usr/bin/env python3
"""
Update player current_team_id based on their most recent game stats.

This ensures players are linked to their current teams for prediction generation.
"""
import sys
from pathlib import Path
from datetime import date

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.database import SessionLocal
from app.models import Player, PlayerGameStat, Game


def update_player_teams():
    """Update current_team_id for all players based on their most recent game."""
    print("🏀 Updating Player Current Teams...")
    print("=" * 60)
    
    db: Session = SessionLocal()
    
    try:
        # Get all players
        players = db.query(Player).all()
        
        updated = 0
        not_found = 0
        
        for player in players:
            # Find their most recent game stat
            most_recent_stat = db.query(PlayerGameStat).join(Game).filter(
                PlayerGameStat.player_id == player.player_id
            ).order_by(desc(Game.game_date)).first()
            
            if most_recent_stat and most_recent_stat.team_id:
                # Use the team_id from the most recent game stat
                new_team_id = most_recent_stat.team_id
                
                if player.current_team_id != new_team_id:
                    player.current_team_id = new_team_id
                    updated += 1
            else:
                not_found += 1
        
        db.commit()
        
        print(f"\n✅ Updated: {updated} players")
        print(f"⚠️  No recent games found for: {not_found} players")
        print(f"✅ Total players processed: {len(players)}")
        
        return {
            'success': True,
            'updated': updated,
            'not_found': not_found
        }
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        db.close()


if __name__ == "__main__":
    update_player_teams()
    print("\n✅ Done!")

