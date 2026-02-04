"""
Bankroll Recommendations API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import date, datetime
from app.database import SessionLocal
from app.services.bankroll_recommendation_service import BankrollRecommendationService

router = APIRouter(prefix="/api/bankroll-recommendations", tags=["bankroll-recommendations"])


class GetRecommendationsRequest(BaseModel):
    """Request to get bankroll recommendations."""
    total_bankroll: float
    reserve_amount: float
    game_date: Optional[str] = None  # YYYY-MM-DD format
    risk_tolerance: str = "moderate"  # conservative, moderate, aggressive


@router.post("")
async def get_recommendations(request: GetRecommendationsRequest):
    """Get betting recommendations based on bankroll."""
    db = SessionLocal()
    try:
        service = BankrollRecommendationService(db)
        
        # Parse game date
        game_date = None
        if request.game_date:
            try:
                game_date = datetime.strptime(request.game_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid game_date format. Use YYYY-MM-DD")
        
        # Validate risk tolerance
        if request.risk_tolerance not in ["conservative", "moderate", "aggressive"]:
            raise HTTPException(
                status_code=400,
                detail="risk_tolerance must be one of: conservative, moderate, aggressive"
            )
        
        # Validate amounts
        if request.total_bankroll < 0:
            raise HTTPException(status_code=400, detail="total_bankroll must be >= 0")
        if request.reserve_amount < 0:
            raise HTTPException(status_code=400, detail="reserve_amount must be >= 0")
        if request.reserve_amount > request.total_bankroll:
            raise HTTPException(status_code=400, detail="reserve_amount cannot exceed total_bankroll")
        
        recommendations = service.get_recommendations(
            total_bankroll=request.total_bankroll,
            reserve_amount=request.reserve_amount,
            game_date=game_date,
            risk_tolerance=request.risk_tolerance
        )
        
        return recommendations
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/test")
async def test_recommendations(
    total_bankroll: float = Query(50.0),
    reserve_amount: float = Query(20.0),
    game_date: Optional[str] = Query(None),
    risk_tolerance: str = Query("moderate")
):
    """Test endpoint with query parameters."""
    db = SessionLocal()
    try:
        service = BankrollRecommendationService(db)
        
        game_date_obj = None
        if game_date:
            try:
                game_date_obj = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid game_date format. Use YYYY-MM-DD")
        
        if risk_tolerance not in ["conservative", "moderate", "aggressive"]:
            raise HTTPException(
                status_code=400,
                detail="risk_tolerance must be one of: conservative, moderate, aggressive"
            )
        
        recommendations = service.get_recommendations(
            total_bankroll=total_bankroll,
            reserve_amount=reserve_amount,
            game_date=game_date_obj,
            risk_tolerance=risk_tolerance
        )
        
        return recommendations
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()




