#!/usr/bin/env python3
"""
MLB version of the master script to update all MLB betting analytics data.

Usage:
    python scripts/mlb_update_all.py

This script will:
1. Update MLB game schedules (next 30 days, including postseason) and Game rows
2. Update MLB game results (previous day)
3. Generate MLB predictions for upcoming games
4. Evaluate MLB predictions for finished games

FIRST-TIME SETUP - Historical backfill (run once to get player stats for predictions):
    python scripts/mlb_collect_game_results.py --season 2025 --days 90
    # Or specific range: --start-date 2025-03-20 --end-date 2025-06-01
    # Use --skip-existing to resume if interrupted
"""

import sys
import warnings
from datetime import datetime, date, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

warnings.filterwarnings('ignore', category=UserWarning, module='urllib3')

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mlb_update_log.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def update_schedules():
    logger.info("=" * 60)
    logger.info("STEP 1: Updating MLB schedules...")
    logger.info("=" * 60)
    try:
        import os
        env = os.environ.copy()
        env['PYTHONUTF8'] = '1'  # Force UTF-8 encoding on Windows
        
        result = __import__('subprocess').run(
            [sys.executable, 'scripts/mlb_collect_schedule.py', '--days', '30'],
            capture_output=True, text=True, cwd=project_root, env=env, encoding='utf-8', errors='replace'
        )
        if result.returncode != 0:
            logger.error(f"Schedule update failed: {result.stderr}")
            return False
        logger.info("MLB schedules updated")
        # Safety net: GameSchedule → Game (predictions/suggested bets query games).
        # mlb_collect_schedule now writes Game rows itself; this catches leftovers.
        from scripts.create_games_from_schedules import create_games_from_schedules
        game_result = create_games_from_schedules(days_ahead=30, sport='MLB')
        if not game_result.get('success'):
            logger.error(f"Creating Game records from schedules failed: {game_result.get('error')}")
            return False
        logger.info(
            f"Game records from schedules: created={game_result.get('created', 0)} "
            f"linked={game_result.get('updated', 0)}"
        )
        return True
    except Exception as e:
        logger.error(f"Error: {e}")
        return False


def update_game_results():
    logger.info("=" * 60)
    logger.info("STEP 2: Updating MLB game results...")
    logger.info("=" * 60)
    try:
        import os
        env = os.environ.copy()
        env['PYTHONUTF8'] = '1'  # Force UTF-8 encoding on Windows
        
        result = __import__('subprocess').run(
            [sys.executable, 'scripts/mlb_collect_game_results.py', '--previous-day'],
            capture_output=True, text=True, cwd=project_root, env=env, encoding='utf-8', errors='replace'
        )
        if result.returncode == 0:
            logger.info("MLB game results updated")
            return True
        logger.error(f"Game results update failed: {result.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error: {e}")
        return False


def generate_predictions():
    logger.info("=" * 60)
    logger.info("STEP 3: Generating MLB predictions...")
    logger.info("=" * 60)
    try:
        import os
        env = os.environ.copy()
        env['PYTHONUTF8'] = '1'  # Force UTF-8 encoding on Windows
        
        result = __import__('subprocess').run(
            [sys.executable, 'scripts/generate_mlb_predictions.py', '--upcoming'],
            capture_output=True, text=True, cwd=project_root, env=env, encoding='utf-8', errors='replace'
        )
        if result.returncode == 0:
            logger.info("MLB predictions generated")
            return True
        logger.error(f"Prediction generation failed: {result.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error: {e}")
        return False


def evaluate_predictions():
    logger.info("=" * 60)
    logger.info("STEP 4: Evaluating MLB predictions...")
    logger.info("=" * 60)
    try:
        import sys
        from pathlib import Path
        # Ensure app module is importable
        backend_path = Path(__file__).parent.parent / "backend"
        if str(backend_path) not in sys.path:
            sys.path.insert(0, str(backend_path))
        
        from app.services.prediction_evaluator import PredictionEvaluator
        from app.database import SessionLocal
        from app.models.prediction import Prediction
        from app.models.game import Game
        from sqlalchemy import and_, distinct

        db = SessionLocal()
        cutoff = date.today() - timedelta(days=7)
        finished = db.query(distinct(Game.game_id), Game.game_date).join(
            Prediction, Game.game_id == Prediction.game_id
        ).filter(
            Game.game_status == 'finished',
            Game.game_date >= cutoff,
            Game.sport == 'MLB',
            Prediction.actual_result.is_(None),
            Prediction.bet_type != 'pass'
        ).order_by(Game.game_date.desc()).all()

        if not finished:
            logger.info("No finished MLB games with unevaluated predictions")
            db.close()
            return True

        evaluator = PredictionEvaluator(db)
        for game_id, _ in finished:
            try:
                evaluator.evaluate_game(game_id)
                db.commit()
            except Exception as e:
                logger.warning(f"Error evaluating game {game_id}: {e}")
                db.rollback()
        db.close()
        logger.info("MLB prediction evaluation complete")
        return True
    except Exception as e:
        logger.error(f"Evaluation error: {e}")
        # Return False on error so summary shows FAILED
        return False


def main():
    logger.info("")
    logger.info("MLB Betting Analytics - Full Update")
    logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    steps = [
        ("MLB Schedules", update_schedules),
        ("MLB Game Results", update_game_results),
        ("MLB Predictions", generate_predictions),
        ("MLB Evaluate Predictions", evaluate_predictions),
    ]
    results = {}
    for name, fn in steps:
        try:
            success = fn()
            results[name] = success
            if not success:
                logger.error(f"Step '{name}' reported failure")
        except Exception as e:
            logger.error(f"Exception in {name}: {e}")
            results[name] = False

    logger.info("")
    logger.info("=" * 60)
    logger.info("MLB UPDATE SUMMARY")
    logger.info("=" * 60)
    all_ok = True
    for name, ok in results.items():
        status = 'OK' if ok else 'FAILED'
        logger.info(f"  {name}: {status}")
        if not ok:
            all_ok = False
    logger.info("=" * 60)
    logger.info(f"Overall: {'SUCCESS' if all_ok else 'FAILED'}")
    logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
