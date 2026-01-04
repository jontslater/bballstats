#!/usr/bin/env python3
"""
Update game statuses for past games.

Marks games from previous days as 'finished' if they're still marked as 'scheduled'.
"""
import sys
from pathlib import Path
from datetime import date, timedelta

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models import Game, GameSchedule


def update_game_statuses():
    """Update game statuses for past games and today's games based on game times."""
    print("🔄 Updating Game Statuses...")
    print("=" * 60)
    
    db: Session = SessionLocal()
    
    try:
        from datetime import datetime, timezone
        today = date.today()
        now = datetime.now(timezone.utc)
        
        games_updated = 0
        schedules_updated = 0
        
        # Update Game records - mark past games as finished
        past_games = db.query(Game).filter(
            and_(
                Game.game_date < today,
                Game.game_status.in_(['scheduled', 'in_progress'])
            )
        ).all()
        
        for game in past_games:
            game.game_status = 'finished'
            games_updated += 1
        
        # Update today's games - check NBA API for actual status
        today_games = db.query(Game).filter(
            and_(
                Game.game_date == today,
                Game.game_status == 'scheduled'
            )
        ).all()
        
        if today_games:
            try:
                from app.scrapers.nba_api_client import NBAAPIClient
                client = NBAAPIClient()
                games_data = client.get_game_schedule(today)
                
                # Create a mapping of NBA game IDs to status
                nba_status_map = {}
                for gd in games_data:
                    nba_game_id = gd.get('GAME_ID')
                    status_text = str(gd.get('GAME_STATUS_TEXT', '')).upper()
                    status_id = gd.get('GAME_STATUS_ID', 0)
                    
                    if 'FINAL' in status_text or status_id == 3:
                        nba_status_map[nba_game_id] = 'finished'
                    elif 'LIVE' in status_text or status_id == 2:
                        nba_status_map[nba_game_id] = 'in_progress'
                    else:
                        nba_status_map[nba_game_id] = 'scheduled'
                
                # Update games based on NBA API status
                for game in today_games:
                    schedule = db.query(GameSchedule).filter(
                        GameSchedule.game_id == game.game_id
                    ).first()
                    
                    if schedule and schedule.nba_game_id:
                        nba_status = nba_status_map.get(schedule.nba_game_id)
                        if nba_status and nba_status != game.game_status:
                            game.game_status = nba_status
                            games_updated += 1
                            
                            # Also update schedule
                            if schedule:
                                schedule.status = nba_status
                                schedules_updated += 1
            except Exception as e:
                print(f"⚠️  Could not check NBA API for game statuses: {e}")
                # Fall back to time-based logic if API fails
                for game in today_games:
                    schedule = db.query(GameSchedule).filter(
                        GameSchedule.game_id == game.game_id
                    ).first()
                    
                    if schedule and schedule.game_time:
                        game_time = schedule.game_time
                        # Skip if game_time is midnight (placeholder)
                        if game_time.hour == 0 and game_time.minute == 0:
                            continue
                            
                        if game_time.tzinfo is None:
                            time_diff = now.replace(tzinfo=None) - game_time
                            if time_diff.total_seconds() > 10800:  # 3 hours
                                game.game_status = 'finished'
                                games_updated += 1
                            elif time_diff.total_seconds() > -1800:  # Started
                                game.game_status = 'in_progress'
                                games_updated += 1
        
        # Update GameSchedule records - mark past schedules as finished
        past_schedules = db.query(GameSchedule).filter(
            and_(
                GameSchedule.game_date < today,
                GameSchedule.status.in_(['scheduled', 'in_progress'])
            )
        ).all()
        
        for schedule in past_schedules:
            schedule.status = 'finished'
            schedules_updated += 1
        
        # Update today's schedules based on game time
        today_schedules = db.query(GameSchedule).filter(
            and_(
                GameSchedule.game_date == today,
                GameSchedule.status == 'scheduled'
            )
        ).all()
        
        for schedule in today_schedules:
            if schedule.game_time:
                game_time = schedule.game_time
                if game_time.tzinfo is None:
                    time_diff = now.replace(tzinfo=None) - game_time
                    if time_diff.total_seconds() > 10800:  # 3 hours
                        schedule.status = 'finished'
                        schedules_updated += 1
                    elif time_diff.total_seconds() > -1800:  # Started
                        schedule.status = 'in_progress'
                        schedules_updated += 1
        
        db.commit()
        
        print(f"✅ Updated {games_updated} Game records")
        print(f"✅ Updated {schedules_updated} GameSchedule records")
        print(f"✅ Games before {today} are now marked as 'finished'")
        print(f"✅ Today's games updated based on game times")
        
        return {
            'success': True,
            'games_updated': games_updated,
            'schedules_updated': schedules_updated
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
    update_game_statuses()
    print("\n✅ Done!")

