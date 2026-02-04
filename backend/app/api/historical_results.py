"""
Historical Results API endpoints.

Track and analyze performance of suggested bets and parlays over time.
"""
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, Body
from sqlalchemy.orm import Session
from typing import Optional, Dict, List
from datetime import date, datetime
from app.database import SessionLocal
from app.services.historical_tracking_service import HistoricalTrackingService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/historical-results", tags=["historical-results"])


@router.post("/update-results")
async def update_historical_results(
    game_date: Optional[str] = Query(None, description="Specific date to update (YYYY-MM-DD). If not provided, updates yesterday's results")
):
    """
    Update historical results for bets and parlays from completed games.

    This endpoint should be called after games have finished to update the hit/miss status.
    """
    db = SessionLocal()
    try:
        service = HistoricalTrackingService(db)

        # Default to yesterday if no date provided
        if game_date:
            try:
                target_date = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        else:
            # Always update yesterday's results since games finish after midnight
            target_date = date.today() - timedelta(days=1)

        results = service.update_results(target_date)

        return {
            "success": True,
            "message": f"Updated results for {target_date}",
            "bets_updated": results['bets_updated'],
            "parlays_updated": results['parlays_updated'],
            "target_date": target_date.isoformat()
        }

    except Exception as e:
        logger.error(f"Error updating historical results: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update results: {str(e)}")
    finally:
        db.close()


@router.get("/performance")
async def get_performance_stats(
    days_back: int = Query(30, description="Number of days back to analyze")
):
    """
    Get overall performance statistics for suggested bets and parlays.
    """
    db = SessionLocal()
    try:
        service = HistoricalTrackingService(db)
        stats = service.get_historical_performance(days_back)

        return {
            "success": True,
            "performance": stats,
            "analyzed_period": f"Last {days_back} days"
        }

    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get performance stats: {str(e)}")
    finally:
        db.close()


@router.get("/recent-results")
async def get_recent_results(
    limit: int = Query(50, description="Maximum number of results to return")
):
    """
    Get recent betting results for display.
    """
    db = SessionLocal()
    try:
        service = HistoricalTrackingService(db)
        results = service.get_recent_results(limit)

        return {
            "success": True,
            "results": results,
            "total_results": len(results['suggested_bets']) + len(results['parlays'])
        }

    except Exception as e:
        logger.error(f"Error getting recent results: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recent results: {str(e)}")
    finally:
        db.close()


@router.post("/save-suggested-bets")
async def save_suggested_bets(
    request: Dict = Body(...)
):
    """
    Save suggested bets to historical tracking.

    This is typically called automatically after bet generation.
    """
    db = SessionLocal()
    try:
        service = HistoricalTrackingService(db)

        # Extract data from request
        bets = request.get('bets', [])
        date_filter = request.get('date_filter', str(date.today()))

        logger.info(f"Saving suggested bets: {len(bets)} bets, date={date_filter}")

        try:
            target_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()

        saved_count = service.save_suggested_bets(bets, target_date)

        return {
            "success": True,
            "message": f"Saved {saved_count} suggested bets to historical tracking",
            "saved_count": saved_count
        }

    except Exception as e:
        logger.error(f"Error saving suggested bets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save suggested bets: {str(e)}")
    finally:
        db.close()


@router.post("/save-parlay")
async def save_parlay(
    request: Dict = Body(...)
):
    """
    Save a parlay to historical tracking.

    This is typically called automatically after parlay generation.
    """
    db = SessionLocal()
    try:
        service = HistoricalTrackingService(db)

        # Extract data from request
        parlay_data = request.get('parlay_data', {})
        legs = request.get('legs', [])
        parlay_type = request.get('parlay_type', 'unknown')

        logger.info(f"Saving parlay: type={parlay_type}, legs={len(legs)}, data_keys={list(parlay_data.keys())}")

        parlay_id = service.save_parlay(parlay_data, legs, parlay_type)

        return {
            "success": True,
            "message": f"Saved {parlay_type} parlay to historical tracking",
            "parlay_id": parlay_id
        }

    except Exception as e:
        logger.error(f"Error saving parlay: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save parlay: {str(e)}")
    finally:
        db.close()