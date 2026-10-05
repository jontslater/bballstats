#!/usr/bin/env python3
"""
Create Game records from GameSchedule records for upcoming games.

This allows the prediction service to work with upcoming games.
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
from app.models import GameSchedule, Game, Season


def create_games_from_schedules(days_ahead: int = 7, sport: str = None):
    """
    Create Game records from GameSchedule records for upcoming games.
    
    This is needed because the prediction service works with Game records,
    not GameSchedule records.
    """
    print("🏀 Creating Game records from GameSchedule...")
    print("=" * 60)
    
    db: Session = SessionLocal()
    
    try:
        today = date.today()
        end_date = today + timedelta(days=days_ahead)
        
        # Get all scheduled games that don't have Game records yet
        filters = [
            GameSchedule.game_date >= today,
            GameSchedule.game_date <= end_date,
            GameSchedule.status.in_(['scheduled', 'in_progress']),
            GameSchedule.game_id.is_(None),  # No Game record linked yet
        ]
        if sport:
            filters.append(GameSchedule.sport == sport)

        schedules = db.query(GameSchedule).filter(and_(*filters)).all()
        
        created = 0
        updated = 0
        
        for schedule in schedules:
            external_id = schedule.external_game_id or schedule.nba_game_id

            existing_game = None
            if external_id:
                existing_game = db.query(Game).filter(
                    Game.sport == schedule.sport,
                    Game.espn_game_id == external_id,
                ).first()
            if not existing_game:
                existing_game = db.query(Game).filter(
                    and_(
                        Game.sport == schedule.sport,
                        Game.game_date == schedule.game_date,
                        Game.home_team_id == schedule.home_team_id,
                        Game.away_team_id == schedule.away_team_id
                    )
                ).first()
            
            if existing_game:
                # Link the schedule to the existing game
                schedule.game_id = existing_game.game_id
                if external_id and not existing_game.espn_game_id:
                    existing_game.espn_game_id = external_id
                updated += 1
            else:
                # Create new Game record (inherit sport from season)
                season = db.query(Season).filter(Season.season_id == schedule.season_id).first()
                game_sport = season.sport if season else schedule.sport
                
                game = Game(
                    sport=game_sport,
                    game_date=schedule.game_date,
                    season_id=schedule.season_id,
                    home_team_id=schedule.home_team_id,
                    away_team_id=schedule.away_team_id,
                    game_status=schedule.status,
                    espn_game_id=external_id,
                )
                db.add(game)
                db.flush()  # Get the game_id
                
                # Link schedule to game
                schedule.game_id = game.game_id
                created += 1
        
        db.commit()
        
        print(f"\n✅ Created: {created} Game records")
        print(f"✅ Updated: {updated} GameSchedule links")
        print(f"✅ Total schedules processed: {len(schedules)}")
        
        return {
            'success': True,
            'created': created,
            'updated': updated
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
    import argparse
    
    parser = argparse.ArgumentParser(description='Create Game records from GameSchedule')
    parser.add_argument('--days', type=int, default=7, help='Number of days ahead to process')
    
    args = parser.parse_args()
    
    create_games_from_schedules(days_ahead=args.days)
    print("\n✅ Done!")





