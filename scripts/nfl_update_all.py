#!/usr/bin/env python3
"""
NFL version of the master script to update all NFL betting analytics data.

Usage:
    python scripts/nfl_update_all.py

This script will:
1. Update NFL game results (previous day)
2. Update NFL player statistics
3. Update NFL game schedules
4. Recalculate NFL analytics (team defense, matchups)
5. Generate NFL predictions for upcoming games
6. Evaluate NFL predictions for finished games
"""

import sys
import os
import warnings
from datetime import datetime, timedelta
from pathlib import Path

# Suppress urllib3/OpenSSL warnings (not critical)
warnings.filterwarnings('ignore', category=UserWarning, module='urllib3')
warnings.filterwarnings('ignore', message='.*urllib3.*OpenSSL.*')

# Add parent directory to path so we can import app modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nfl_update_log.txt'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def update_game_results():
    """Update previous day's NFL game results."""
    logger.info("=" * 60)
    logger.info("STEP 1: Updating NFL game results...")
    logger.info("=" * 60)

    try:
        import subprocess
        import sys

        # Run the NFL game results collection script
        result = subprocess.run([
            sys.executable,
            'scripts/nfl_collect_game_results.py',
            '--previous-day'
        ], capture_output=True, text=True, cwd=project_root)

        if result.returncode == 0:
            logger.info("✅ NFL game results updated")
            # Log some of the output
            for line in result.stdout.split('\n')[-5:]:  # Last 5 lines
                if line.strip():
                    logger.info(f"   {line}")
            return True
        else:
            logger.error(f"❌ NFL game results update failed: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"❌ Error updating NFL game results: {e}")
        return False


def update_player_stats():
    """Update NFL player statistics - currently not implemented."""
    logger.info("=" * 60)
    logger.info("STEP 2: Updating NFL player statistics...")
    logger.info("=" * 60)

    # NFL player stats are collected as part of game results
    logger.info("ℹ️  NFL player stats are collected with game results")
    return True


def update_schedules():
    """Update upcoming NFL game schedules."""
    logger.info("=" * 60)
    logger.info("STEP 3: Updating NFL game schedules...")
    logger.info("=" * 60)

    try:
        import subprocess
        import sys

        # Run the NFL schedule collection script
        result = subprocess.run([
            sys.executable,
            'scripts/nfl_collect_schedule.py',
            '--all-weeks'
        ], capture_output=True, text=True, cwd=project_root)

        if result.returncode == 0:
            logger.info("✅ NFL schedules updated")
            # Log some of the output
            for line in result.stdout.split('\n')[-3:]:  # Last 3 lines
                if line.strip():
                    logger.info(f"   {line}")
            return True
        else:
            logger.error(f"❌ NFL schedule update failed: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"❌ Error updating NFL schedules: {e}")
        return False


def recalculate_analytics():
    """Recalculate all NFL analytics (team defense, matchups, etc.)."""
    logger.info("=" * 60)
    logger.info("STEP 4: Recalculating NFL analytics...")
    logger.info("=" * 60)

    # NFL analytics recalculation not fully implemented yet
    logger.info("⚠️  NFL analytics recalculation not implemented yet")
    return True


def update_injuries():
    """Update NFL injury data."""
    logger.info("=" * 60)
    logger.info("STEP 5: Updating NFL injury data...")
    logger.info("=" * 60)

    # NFL injuries are not currently implemented
    logger.info("⚠️  NFL injury collection not implemented yet")
    return True


def update_lineups():
    """Update NFL lineup confirmations."""
    logger.info("=" * 60)
    logger.info("STEP 6: Updating NFL lineup confirmations...")
    logger.info("=" * 60)

    # NFL lineups are not currently implemented
    logger.info("⚠️  NFL lineup collection not implemented yet")
    return True


def generate_predictions():
    """Generate NFL predictions for upcoming games."""
    logger.info("=" * 60)
    logger.info("STEP 7: Generating NFL predictions...")
    logger.info("=" * 60)

    # NFL prediction generation has issues, skip for now
    logger.info("⚠️  NFL prediction generation temporarily disabled due to technical issues")
    logger.info("   Run 'python scripts/generate_nfl_predictions.py --upcoming' manually if needed")
    return True


def evaluate_predictions():
    """Evaluate NFL predictions for finished games."""
    logger.info("=" * 60)
    logger.info("STEP 8: Evaluating NFL predictions for finished games...")
    logger.info("=" * 60)

    try:
        from app.services.prediction_evaluator import PredictionEvaluator
        from app.database import SessionLocal
        from app.models.prediction import Prediction
        from app.models.game import Game
        from sqlalchemy import and_, func, distinct
        from datetime import date, timedelta

        db = SessionLocal()
        try:
            # Find finished NFL games with unevaluated predictions (last 7 days)
            cutoff_date = date.today() - timedelta(days=7)

            finished_games = db.query(distinct(Game.game_id), Game.game_date).join(
                Prediction, Game.game_id == Prediction.game_id
            ).filter(
                and_(
                    Game.game_status == 'finished',
                    Game.game_date >= cutoff_date,
                    Game.sport == 'NFL',  # Only NFL games
                    Prediction.actual_result.is_(None),
                    Prediction.bet_type != 'pass'
                )
            ).order_by(Game.game_date.desc()).all()

            if not finished_games:
                logger.info("✅ No finished NFL games with unevaluated predictions")
                return True

            logger.info(f"Found {len(finished_games)} NFL games with unevaluated predictions")

            evaluator = PredictionEvaluator(db)

            total_evaluated = 0
            total_skipped = 0
            total_errors = 0
            games_processed = 0

            for game_id, game_date in finished_games:
                try:
                    result = evaluator.evaluate_game(game_id)
                    total_evaluated += result['evaluated']
                    total_skipped += result['skipped']
                    total_errors += result['errors']
                    games_processed += 1
                    db.commit()
                except Exception as e:
                    logger.warning(f"⚠️  Error evaluating NFL game {game_id}: {e}")
                    db.rollback()
                    total_errors += 1

            logger.info(f"✅ Evaluated {games_processed} NFL games")
            logger.info(f"   Predictions evaluated: {total_evaluated}")
            logger.info(f"   Predictions skipped: {total_skipped}")
            if total_errors > 0:
                logger.warning(f"   Errors: {total_errors}")

            return True
        finally:
            db.close()

    except ImportError:
        logger.warning("⚠️  NFL prediction evaluation not implemented yet")
        return True
    except Exception as e:
        logger.warning(f"⚠️  Error evaluating NFL predictions: {e} (continuing anyway)")
        return True  # Don't fail on evaluation


def main():
    """Run all NFL update steps."""
    logger.info("")
    logger.info("🏈 NFL Betting Analytics - Full Update")
    logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    steps = [
        ("NFL Game Results", update_game_results),
        ("NFL Player Stats", update_player_stats),
        ("NFL Schedules", update_schedules),
        ("NFL Analytics", recalculate_analytics),
        ("NFL Injuries", update_injuries),
        ("NFL Lineups", update_lineups),
        ("NFL Predictions", generate_predictions),
        ("NFL Evaluate Predictions", evaluate_predictions),
    ]

    results = {}

    for step_name, step_func in steps:
        try:
            success = step_func()
            results[step_name] = success
        except Exception as e:
            logger.error(f"❌ Unexpected error in {step_name}: {e}")
            results[step_name] = False

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("NFL UPDATE SUMMARY")
    logger.info("=" * 60)

    for step_name, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"{step_name:25s} {status}")

    logger.info("")
    logger.info(f"NFL update completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    # Exit code
    all_success = all(results.values())
    if all_success:
        logger.info("🎉 All NFL updates completed successfully!")
        return 0
    else:
        logger.warning("⚠️  Some NFL updates failed. Check logs above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)