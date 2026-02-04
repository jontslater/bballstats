"""
ML Training API endpoints.

Endpoints for training and retraining ML models to optimize predictions.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, timedelta
from app.database import SessionLocal
from app.services.ml_optimizer import MLOptimizer

router = APIRouter(prefix="/api/ml", tags=["ml-training"])


@router.post("/train")
async def train_models(
    days_back: int = 90,
    min_predictions: int = 100
):
    """
    Train ML models to optimize prediction accuracy.
    
    Args:
        days_back: Number of days of historical data to use (default: 90)
        min_predictions: Minimum number of predictions needed (default: 100)
    
    Returns:
        Training results including model performance and calibration data
    """
    db = SessionLocal()
    try:
        optimizer = MLOptimizer(db)
        
        # Collect training data
        end_date = date.today() - timedelta(days=1)  # Yesterday
        start_date = end_date - timedelta(days=days_back)
        
        training_data_result = optimizer.collect_training_data(
            start_date=start_date,
            end_date=end_date,
            min_predictions=min_predictions
        )
        
        if 'error' in training_data_result:
            raise HTTPException(
                status_code=400,
                detail=training_data_result['error']
            )
        
        training_data = training_data_result.get('data', [])
        
        if len(training_data) < min_predictions:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient training data: {len(training_data)} predictions (need {min_predictions})"
            )
        
        # Train models
        optimization_result = optimizer.optimize_factor_weights(training_data)
        
        if 'error' in optimization_result:
            raise HTTPException(
                status_code=500,
                detail=optimization_result['error']
            )
        
        # Calibrate probabilities
        calibration_result = optimizer.calibrate_probabilities(training_data)
        
        return {
            "success": True,
            "training_data_count": len(training_data),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "optimization": optimization_result,
            "calibration": calibration_result,
            "message": "Models trained successfully. Calibration data will be used in future predictions."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error training models: {str(e)}")
    finally:
        db.close()


@router.get("/calibration-status")
async def get_calibration_status():
    """
    Get current calibration status and statistics.
    
    Returns:
        Information about calibration data availability
    """
    db = SessionLocal()
    try:
        optimizer = MLOptimizer(db)
        
        # Check if we have enough data for calibration
        training_data_result = optimizer.collect_training_data(min_predictions=100)
        
        has_data = 'error' not in training_data_result
        data_count = training_data_result.get('count', 0) if has_data else 0
        
        return {
            "has_sufficient_data": has_data and data_count >= 100,
            "available_predictions": data_count,
            "min_required": 100,
            "message": "Calibration is applied automatically when sufficient data is available"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking calibration status: {str(e)}")
    finally:
        db.close()





