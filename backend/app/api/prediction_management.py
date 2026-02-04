"""
Prediction Management API endpoints.

Endpoints for updating predictions with results and viewing calibration statistics.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
from app.database import SessionLocal
from app.services.prediction_calibration import PredictionCalibration

router = APIRouter(prefix="/api/prediction-management", tags=["prediction-management"])


@router.post("/update-results")
async def update_prediction_results(game_date: Optional[str] = None):
    """
    Update predictions with actual game results.
    
    Args:
        game_date: Optional date (YYYY-MM-DD) to update. If not provided, updates all finished games.
    
    Returns:
        Update statistics
    """
    db = SessionLocal()
    try:
        calibration = PredictionCalibration(db)
        
        parsed_date = None
        if game_date:
            try:
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        result = calibration.update_predictions_with_results(parsed_date)
        return result
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating results: {str(e)}")
    finally:
        db.close()


@router.get("/calibration-stats")
async def get_calibration_stats():
    """
    Get overall calibration statistics.
    
    Returns:
        Dict with calibration statistics by bet type
    """
    db = SessionLocal()
    try:
        calibration = PredictionCalibration(db)
        stats = calibration.get_calibration_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting calibration stats: {str(e)}")
    finally:
        db.close()


@router.get("/calibration-curves")
async def get_calibration_curves():
    """
    Get detailed calibration curves.
    
    Returns:
        Dict with calibration curves by bet type and probability range
    """
    db = SessionLocal()
    try:
        calibration = PredictionCalibration(db)
        curves = calibration.calculate_calibration_curves()
        return curves
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting calibration curves: {str(e)}")
    finally:
        db.close()

