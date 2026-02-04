"""
Betting Lines API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.database import SessionLocal
from app.services.betting_line_service import BettingLineService
from pydantic import BaseModel

router = APIRouter(prefix="/api/betting-lines", tags=["betting-lines"])


class AddBettingLineRequest(BaseModel):
    game_id: int
    player_id: int
    stat_type: str
    over_line: float
    over_odds: str = "-110"
    under_odds: str = "-110"
    sportsbook: str = "DraftKings"


@router.post("/add")
async def add_betting_line(request: AddBettingLineRequest):
    """Add or update a betting line."""
    db = SessionLocal()
    try:
        service = BettingLineService(db)
        betting_line = service.add_betting_line(
            game_id=request.game_id,
            player_id=request.player_id,
            stat_type=request.stat_type,
            over_line=request.over_line,
            over_odds=request.over_odds,
            under_odds=request.under_odds,
            sportsbook=request.sportsbook
        )
        
        return {
            "success": True,
            "betting_line_id": betting_line.line_id,
            "message": "Betting line added/updated"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/value-bets")
async def get_value_bets(
    game_id: Optional[int] = Query(None, description="Filter by game ID"),
    stat_type: Optional[str] = Query(None, description="Filter by stat type"),
    min_value_score: float = Query(0.02, description="Minimum value score (0.02 = 2% edge)")
):
    """Find bets where our predictions show value vs betting lines."""
    db = SessionLocal()
    try:
        service = BettingLineService(db)
        value_bets = service.find_value_bets(
            game_id=game_id,
            stat_type=stat_type,
            min_value_score=min_value_score
        )
        
        return value_bets
    finally:
        db.close()


@router.get("/compare/{prediction_id}/{betting_line_id}")
async def compare_prediction_to_line(
    prediction_id: int,
    betting_line_id: int
):
    """Compare a specific prediction to a betting line."""
    db = SessionLocal()
    try:
        service = BettingLineService(db)
        comparison = service.compare_prediction_to_line(
            prediction_id=prediction_id,
            betting_line_id=betting_line_id
        )
        
        return comparison
    finally:
        db.close()





