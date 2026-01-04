#!/usr/bin/env python3
"""
Quick update script - just the essentials.

Usage:
    python scripts/quick_update.py
    
This is a faster version that only updates:
- Previous day's game results
- Predictions for today's games
"""

import sys
import os
import warnings
from datetime import datetime
from pathlib import Path

# Suppress urllib3/OpenSSL warnings (not critical)
warnings.filterwarnings('ignore', category=UserWarning, module='urllib3')
warnings.filterwarnings('ignore', message='.*urllib3.*OpenSSL.*')

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import traceback
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Quick update - just essentials."""
    logger.info("🏀 Quick Update - Essentials Only")
    logger.info("")
    
    # Step 1: Update yesterday's games
    logger.info("Updating yesterday's game results...")
    try:
        from scripts.collect_game_results import collect_previous_day_games
        collect_previous_day_games()  # Uses yesterday by default
        logger.info("✅ Game results updated")
    except Exception as e:
        import traceback
        logger.warning(f"⚠️  Could not update games: {e}")
        logger.debug(traceback.format_exc())
    
    # Step 2: Evaluate yesterday's predictions (if games finished)
    logger.info("Evaluating predictions for finished games...")
    try:
        from app.services.prediction_evaluator import PredictionEvaluator
        from app.database import SessionLocal
        from app.models.prediction import Prediction
        from app.models.game import Game
        from sqlalchemy import and_, distinct
        from datetime import date, timedelta
        
        db = SessionLocal()
        try:
            # Evaluate yesterday's games
            yesterday = date.today() - timedelta(days=1)
            evaluator = PredictionEvaluator(db)
            result = evaluator.evaluate_date(yesterday)
            
            if result.get('evaluated', 0) > 0:
                logger.info(f"✅ Evaluated {result['evaluated']} predictions for yesterday's games")
            else:
                logger.info("   No predictions to evaluate (games may not have finished or stats not available)")
        finally:
            db.close()
    except Exception as e:
        import traceback
        logger.warning(f"⚠️  Could not evaluate predictions: {e}")
        logger.debug(traceback.format_exc())
    
    # Step 3: Regenerate today's predictions
    logger.info("Regenerating predictions for today's games...")
    try:
        from app.services.prediction_service import PredictionService
        from app.database import SessionLocal
        
        db = SessionLocal()
        try:
            service = PredictionService(db)
            results = service.generate_predictions_for_upcoming_games(days_ahead=1)
            logger.info(f"✅ Generated predictions for {results['games_processed']} games")
            logger.info(f"   Created: {results['created']}, Updated: {results['updated']}")
        finally:
            db.close()
    except Exception as e:
        import traceback
        logger.warning(f"⚠️  Could not generate predictions: {e}")
        logger.debug(traceback.format_exc())
    
    logger.info("")
    logger.info("✅ Quick update complete!")


if __name__ == "__main__":
    main()

