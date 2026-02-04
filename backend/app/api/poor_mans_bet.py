"""
Poor Man's Bet API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from app.database import SessionLocal
from app.models.poor_mans_bet import PoorMansBetChallenge, PoorMansBetDay
from app.services.poor_mans_bet_service import PoorMansBetService
from pydantic import BaseModel

router = APIRouter(prefix="/api/poor-mans-bet", tags=["poor-mans-bet"])


class CreateChallengeRequest(BaseModel):
    """Request to create a new challenge."""
    start_amount: float
    days_target: int = 14
    name: Optional[str] = None


class PlaceBetRequest(BaseModel):
    """Request to place a bet for a day."""
    prediction_ids: List[int]  # List of prediction IDs for the bet legs
    bet_amount: float
    game_date: str  # YYYY-MM-DD
    notes: Optional[str] = None


class ResolveBetRequest(BaseModel):
    """Request to resolve a bet."""
    status: str  # 'hit' or 'miss'
    actual_return: Optional[float] = None


@router.post("/challenges")
async def create_challenge(request: CreateChallengeRequest):
    """Create a new Poor Man's Bet challenge."""
    db = SessionLocal()
    try:
        if request.start_amount < 1.0 or request.start_amount > 5.0:
            raise HTTPException(status_code=400, detail="Start amount must be between $1 and $5")
        
        if request.days_target < 1 or request.days_target > 30:
            raise HTTPException(status_code=400, detail="Days target must be between 1 and 30")
        
        service = PoorMansBetService(db)
        challenge = service.create_challenge(
            start_amount=Decimal(str(request.start_amount)),
            days_target=request.days_target,
            name=request.name
        )
        
        return {
            "challenge_id": challenge.challenge_id,
            "name": challenge.name,
            "start_amount": float(challenge.start_amount),
            "target_amount": float(challenge.target_amount),
            "days_target": challenge.days_target,
            "current_bankroll": float(challenge.current_bankroll),
            "status": challenge.status,
            "start_date": challenge.start_date.isoformat(),
            "target_date": challenge.target_date.isoformat() if challenge.target_date else None
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/challenges")
async def get_challenges(
    status: Optional[str] = Query(None, description="Filter by status (active, completed, failed)")
):
    """Get all Poor Man's Bet challenges."""
    db = SessionLocal()
    try:
        query = db.query(PoorMansBetChallenge)
        
        if status:
            query = query.filter(PoorMansBetChallenge.status == status)
        
        challenges = query.order_by(PoorMansBetChallenge.created_at.desc()).all()
        
        return [
            {
                "challenge_id": c.challenge_id,
                "name": c.name,
                "start_amount": float(c.start_amount),
                "target_amount": float(c.target_amount),
                "current_bankroll": float(c.current_bankroll),
                "status": c.status,
                "current_day": c.current_day,
                "days_target": c.days_target,
                "wins": c.wins,
                "losses": c.losses,
                "start_date": c.start_date.isoformat(),
                "target_date": c.target_date.isoformat() if c.target_date else None
            }
            for c in challenges
        ]
    finally:
        db.close()


@router.get("/challenges/{challenge_id}")
async def get_challenge(challenge_id: int):
    """Get challenge status and details."""
    db = SessionLocal()
    try:
        service = PoorMansBetService(db)
        status = service.get_challenge_status(challenge_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        return status
    finally:
        db.close()


@router.get("/challenges/{challenge_id}/eligible-plays")
async def get_eligible_plays(
    challenge_id: int,
    game_date: Optional[str] = Query(None, description="Game date (YYYY-MM-DD), defaults to challenge day")
):
    """Get all eligible plays for a challenge day (all safe bets that meet Poor Man's Bet criteria)."""
    db = SessionLocal()
    try:
        service = PoorMansBetService(db)
        
        # Get challenge to determine current day and calculate date
        challenge = db.query(PoorMansBetChallenge).filter(
            PoorMansBetChallenge.challenge_id == challenge_id
        ).first()
        
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        parsed_date = None
        if game_date:
            try:
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Get all eligible plays for the date
        eligible_plays = service.get_all_eligible_plays(challenge_id, parsed_date)
        
        return {
            "challenge_id": challenge_id,
            "current_day": challenge.current_day,
            "game_date": eligible_plays['game_date'],
            "plays": eligible_plays['plays'],
            "total_count": len(eligible_plays['plays'])
        }
    finally:
        db.close()


@router.post("/challenges/{challenge_id}/suggest-bet")
async def suggest_bet(
    challenge_id: int,
    game_date: Optional[str] = Query(None, description="Game date (YYYY-MM-DD), defaults to today")
):
    """Get suggested bet for a challenge day."""
    db = SessionLocal()
    try:
        service = PoorMansBetService(db)
        
        parsed_date = None
        if game_date:
            try:
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        suggestion = service.get_daily_bet_suggestion(challenge_id, parsed_date, allow_multiple=True)
        
        if not suggestion:
            return {
                "available": False,
                "message": "No safe bets available for this date"
            }
        
        return {
            "available": True,
            **suggestion
        }
    finally:
        db.close()


@router.post("/challenges/{challenge_id}/place-bet")
async def place_bet(challenge_id: int, request: PlaceBetRequest):
    """Place a bet for a challenge day."""
    db = SessionLocal()
    try:
        # Parse date
        try:
            game_date = datetime.strptime(request.game_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        if not request.prediction_ids or len(request.prediction_ids) == 0:
            raise HTTPException(status_code=400, detail="At least one prediction ID is required")
        
        service = PoorMansBetService(db)
        bet_day = service.place_bet(
            challenge_id=challenge_id,
            prediction_ids=request.prediction_ids,
            bet_amount=Decimal(str(request.bet_amount)),
            game_date=game_date,
            notes=request.notes
        )
        
        return {
            "message": "Bet placed successfully",
            "day_id": bet_day.day_id,
            "challenge_id": bet_day.challenge_id,
            "day_number": bet_day.day_number,
            "bet_amount": float(bet_day.bet_amount),
            "bet_type": bet_day.bet_type,
            "status": bet_day.status
        }
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error placing bet: {str(e)}")
    finally:
        db.close()


@router.delete("/challenges/{challenge_id}")
async def delete_challenge(challenge_id: int):
    """Delete a Poor Man's Bet challenge."""
    db = SessionLocal()
    try:
        challenge = db.query(PoorMansBetChallenge).filter(
            PoorMansBetChallenge.challenge_id == challenge_id
        ).first()
        
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        # Delete the challenge (days will be cascade deleted)
        db.delete(challenge)
        db.commit()
        
        return {
            "message": "Challenge deleted successfully",
            "challenge_id": challenge_id
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting challenge: {str(e)}")
    finally:
        db.close()


@router.get("/challenges/{challenge_id}/history")
async def get_challenge_history(challenge_id: int):
    """Get bet history for a challenge."""
    db = SessionLocal()
    try:
        challenge = db.query(PoorMansBetChallenge).filter(
            PoorMansBetChallenge.challenge_id == challenge_id
        ).first()
        
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        days = db.query(PoorMansBetDay).filter(
            PoorMansBetDay.challenge_id == challenge_id
        ).order_by(PoorMansBetDay.day_number).all()
        
        return {
            "challenge_id": challenge_id,
            "days": [
                {
                    "day_id": day.day_id,
                    "day_number": day.day_number,
                    "bet_date": day.bet_date.isoformat(),
                    "starting_bankroll": float(day.starting_bankroll),
                    "bet_amount": float(day.bet_amount),
                    "bet_type": day.bet_type,
                    "status": day.status,
                    "target_return": float(day.target_return) if day.target_return else None,
                    "actual_return": float(day.actual_return) if day.actual_return else None,
                    "ending_bankroll": float(day.ending_bankroll) if day.ending_bankroll else None,
                    "notes": day.notes
                }
                for day in days
            ]
        }
    finally:
        db.close()


@router.put("/challenges/{challenge_id}/resolve-bet/{day_id}")
async def resolve_bet_manually(challenge_id: int, day_id: int, request: ResolveBetRequest):
    """Manually resolve a bet day (mark as hit or miss)."""
    db = SessionLocal()
    try:
        service = PoorMansBetService(db)
        result = service.manual_resolve_bet(
            challenge_id=challenge_id,
            day_id=day_id,
            status=request.status,
            actual_return=Decimal(str(request.actual_return)) if request.actual_return else None
        )
        
        return {
            "message": f"Bet marked as {request.status}",
            "challenge_id": challenge_id,
            "day_id": day_id,
            "status": request.status,
            "updated_bankroll": float(result['updated_bankroll']),
            "challenge_status": result['challenge_status']
        }
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error resolving bet: {str(e)}")
    finally:
        db.close()


@router.post("/challenges/{challenge_id}/next-day")
async def advance_to_next_day(
    challenge_id: int,
    final_bankroll: Optional[float] = Query(None, description="Optional final bankroll amount to set before advancing")
):
    """Manually advance challenge to the next day, optionally updating final bankroll."""
    db = SessionLocal()
    try:
        service = PoorMansBetService(db)
        result = service.advance_to_next_day(challenge_id, final_bankroll)
        
        return {
            "message": "Challenge advanced to next day",
            "challenge_id": challenge_id,
            "new_day": result['new_day'],
            "current_bankroll": float(result['current_bankroll'])
        }
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error advancing challenge: {str(e)}")
    finally:
        db.close()

