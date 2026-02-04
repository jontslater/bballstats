"""
Game API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, timedelta
from app.database import SessionLocal
from app.models.game import Game
from app.models.team import Team
from app.models.prediction import Prediction

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("")
async def get_games(
    game_date: Optional[str] = Query(None, description="Filter by game date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)"),
    limit: int = Query(100, description="Maximum number of results")
):
    """Get list of games."""
    db = SessionLocal()
    try:
        # Validate sport
        if sport not in ['NBA', 'NFL']:
            raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}. Must be 'NBA' or 'NFL'")
        
        query = db.query(Game).filter(Game.sport == sport)
        
        if game_date:
            # Parse date string (YYYY-MM-DD) to date object
            try:
                from datetime import datetime
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
                # Filter by game_date, but also check game_time from schedule if available
                # This handles timezone issues where a game might be on the date boundary
                query = query.filter(Game.game_date == parsed_date)
            except ValueError:
                # Invalid date format, ignore filter
                pass
        
        if status:
            query = query.filter(Game.game_status == status)
        # If filtering by today's date and no status specified, ONLY show scheduled and in_progress games
        # (exclude finished games for today to show only bettable games)
        if game_date and not status:
            from datetime import date as date_type
            parsed_date = None
            try:
                from datetime import datetime
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                pass
            
            # If it's today, only show scheduled/in_progress (bettable games)
            if parsed_date and parsed_date == date_type.today():
                query = query.filter(Game.game_status.in_(['scheduled', 'in_progress']))
            # If it's a past date, show all (including finished)
            # If it's a future date, show scheduled/in_progress
        
        games = query.order_by(Game.game_date, Game.game_id).limit(limit).all()
        
        # Enrich with team names (optimized with batch queries)
        from app.models import GameSchedule
        from sqlalchemy import func
        
        # Batch load all teams (filter by sport)
        team_ids = list(set([g.home_team_id for g in games] + [g.away_team_id for g in games]))
        teams_dict = {t.team_id: t for t in db.query(Team).filter(
            Team.team_id.in_(team_ids),
            Team.sport == sport
        ).all()}
        
        # Batch load all schedules (filter by sport)
        game_ids = [g.game_id for g in games]
        schedules_dict = {s.game_id: s for s in db.query(GameSchedule).filter(
            GameSchedule.game_id.in_(game_ids),
            GameSchedule.sport == sport
        ).all()}
        
        # Batch count predictions (filter by sport)
        pred_counts = db.query(
            Prediction.game_id,
            func.count(Prediction.prediction_id).label('count')
        ).filter(
            Prediction.game_id.in_(game_ids),
            Prediction.sport == sport
        ).group_by(Prediction.game_id).all()
        pred_counts_dict = {pc.game_id: pc.count for pc in pred_counts}
        
        # Build result efficiently
        result = []
        for game in games:
            home_team = teams_dict.get(game.home_team_id)
            away_team = teams_dict.get(game.away_team_id)
            
            # Get prediction count
            pred_count = pred_counts_dict.get(game.game_id, 0)
            
            # Get game time from schedule
            schedule = schedules_dict.get(game.game_id)
            game_time = schedule.game_time if schedule else None
            
            # If filtering by date and game_time exists, verify the game_time date matches
            # This handles timezone issues where a game at 12a might be on the wrong day
            if game_date and game_time:
                try:
                    parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
                    # Get the date from game_time (handles timezone conversion)
                    if game_time.tzinfo:
                        # Has timezone - convert to date in that timezone
                        game_time_date = game_time.date()
                    else:
                        # No timezone - use as-is
                        game_time_date = game_time.date()
                    
                    # If game_time date doesn't match requested date, skip this game
                    # (This can happen when games are stored with 12a times in different timezones)
                    if game_time_date != parsed_date:
                        continue  # Skip games where time puts them on a different calendar day
                except (ValueError, AttributeError):
                    pass  # If date parsing fails or game_time is None, include the game anyway
            
            result.append({
                "game_id": game.game_id,
                "game_date": game.game_date,
                "game_time": game_time.isoformat() if game_time else None,
                "game_status": game.game_status,
                "home_team_id": game.home_team_id,
                "home_team_name": home_team.name if home_team else None,
                "home_team_abbreviation": home_team.abbreviation if home_team else None,
                "away_team_id": game.away_team_id,
                "away_team_name": away_team.name if away_team else None,
                "away_team_abbreviation": away_team.abbreviation if away_team else None,
                "home_score": game.home_score,
                "away_score": game.away_score,
                "prediction_count": pred_count
            })
        
        return result
    finally:
        db.close()


@router.get("/{game_id}")
async def get_game(
    game_id: int,
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get game details."""
    db = SessionLocal()
    try:
        # Validate sport
        if sport not in ['NBA', 'NFL']:
            raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}. Must be 'NBA' or 'NFL'")
        
        game = db.query(Game).filter(
            Game.game_id == game_id,
            Game.sport == sport
        ).first()
        
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        home_team = db.query(Team).filter(
            Team.team_id == game.home_team_id,
            Team.sport == sport
        ).first()
        away_team = db.query(Team).filter(
            Team.team_id == game.away_team_id,
            Team.sport == sport
        ).first()
        
        # Count predictions by type (filter by sport)
        safe_bets = db.query(Prediction).filter(
            Prediction.game_id == game_id,
            Prediction.bet_type == "safe",
            Prediction.sport == sport
        ).count()
        
        long_shots = db.query(Prediction).filter(
            Prediction.game_id == game_id,
            Prediction.bet_type == "long_shot",
            Prediction.sport == sport
        ).count()
        
        return {
            "game_id": game.game_id,
            "game_date": game.game_date,
            "game_status": game.game_status,
            "home_team": {
                "team_id": game.home_team_id,
                "name": home_team.name if home_team else None,
                "abbreviation": home_team.abbreviation if home_team else None,
                "score": game.home_score
            },
            "away_team": {
                "team_id": game.away_team_id,
                "name": away_team.name if away_team else None,
                "abbreviation": away_team.abbreviation if away_team else None,
                "score": game.away_score
            },
            "safe_bets_count": safe_bets,
            "long_shots_count": long_shots
        }
    finally:
        db.close()


@router.get("/upcoming/list")
async def get_upcoming_games(
    days_ahead: int = Query(7, description="Days ahead to look"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get upcoming games."""
    db = SessionLocal()
    try:
        # Validate sport
        if sport not in ['NBA', 'NFL']:
            raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}. Must be 'NBA' or 'NFL'")
        
        today = date.today()
        end_date = today + timedelta(days=days_ahead)
        
        # Only get games from today onwards, exclude past games (filter by sport)
        games = db.query(Game).filter(
            Game.sport == sport,
            Game.game_date >= today,  # Only today and future
            Game.game_date <= end_date,
            Game.game_status.in_(['scheduled', 'in_progress'])
        ).order_by(Game.game_date, Game.game_id).all()
        
        # Enrich with team names
        result = []
        for game in games:
            home_team = db.query(Team).filter(
                Team.team_id == game.home_team_id,
                Team.sport == sport
            ).first()
            away_team = db.query(Team).filter(
                Team.team_id == game.away_team_id,
                Team.sport == sport
            ).first()
            
            # Get game time from schedule if available (filter by sport)
            from app.models import GameSchedule
            schedule = db.query(GameSchedule).filter(
                GameSchedule.game_id == game.game_id,
                GameSchedule.sport == sport
            ).first()
            game_time = schedule.game_time if schedule else None
            
            result.append({
                "game_id": game.game_id,
                "game_date": game.game_date,
                "game_time": game_time.isoformat() if game_time else None,
                "game_status": game.game_status,
                "home_team_id": game.home_team_id,
                "home_team_name": home_team.name if home_team else None,
                "home_team_abbreviation": home_team.abbreviation if home_team else None,
                "away_team_id": game.away_team_id,
                "away_team_name": away_team.name if away_team else None,
                "away_team_abbreviation": away_team.abbreviation if away_team else None,
                "home_team": {
                    "team_id": game.home_team_id,
                    "name": home_team.name if home_team else None,
                    "abbreviation": home_team.abbreviation if home_team else None
                },
                "away_team": {
                    "team_id": game.away_team_id,
                    "name": away_team.name if away_team else None,
                    "abbreviation": away_team.abbreviation if away_team else None
                }
            })
        
        return result
    finally:
        db.close()

