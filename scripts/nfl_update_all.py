#!/usr/bin/env python3
"""
NFL version of the master script to update all NFL betting analytics data.

Usage:
    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python scripts/nfl_update_all.py

This script will:
1. Update NFL schedules (ESPN rolling window) and create Game rows from schedules
2. Update NFL game results + player box scores (7-day lookback via ESPN)
3. Update NFL injuries (ESPN, upcoming week)
4. Generate NFL predictions for upcoming games
5. Write suggested bets to historical_suggested_bets
6. Evaluate NFL predictions for finished games

First-time / weekly history (run once or after DB wipe):
    python scripts/nfl_seed_teams.py
    python scripts/nfl_seed_seasons.py
    PYTHONUTF8=1 python scripts/nfl_backfill_player_stats.py --seasons 2025 2026
"""

import sys
import os
import warnings
from datetime import datetime, date, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("nfl_update_log.txt"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def _utf8_env():
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def update_schedules():
    logger.info("=" * 60)
    logger.info("STEP 1: Updating NFL schedules (ESPN)...")
    logger.info("=" * 60)
    try:
        from app.database import SessionLocal
        from app.models import Season
        from app.scrapers.espn_nfl_client import ESPNNFLClient
        from app.services.nfl_schedule import sync_upcoming_schedule_window
        from scripts.create_games_from_schedules import create_games_from_schedules

        db = SessionLocal()
        try:
            season = db.query(Season).filter(
                Season.sport == "NFL",
                Season.is_current == True,
            ).first()
            if not season:
                season = db.query(Season).filter(Season.sport == "NFL").order_by(
                    Season.season_id.desc()
                ).first()
            if not season:
                logger.error("No NFL season found — run nfl_seed_seasons.py")
                return False

            client = ESPNNFLClient()
            result = sync_upcoming_schedule_window(
                db, client, season, lookback_days=7, days_ahead=21
            )
            logger.info(
                f"ESPN schedule persist: created={result['created']} updated={result['updated']} errors={result['errors']}"
            )

            game_result = create_games_from_schedules(days_ahead=21, sport="NFL")
            if not game_result.get("success"):
                logger.error(f"create_games_from_schedules failed: {game_result.get('error')}")
                return False
            logger.info(
                f"Game rows from schedules: created={game_result.get('created', 0)} linked={game_result.get('updated', 0)}"
            )
            return True
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Schedule update error: {e}")
        return False


def update_game_results():
    logger.info("=" * 60)
    logger.info("STEP 2: Updating NFL game results (7-day lookback)...")
    logger.info("=" * 60)
    try:
        from app.database import SessionLocal
        from app.services.nfl_results import collect_results_lookback

        db = SessionLocal()
        try:
            result = collect_results_lookback(db, lookback_days=7)
            logger.info(
                f"NFL results: games_processed={result['games_processed']} player_rows={result['player_rows']}"
            )
            return True
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Game results error: {e}")
        return False


def update_injuries():
    logger.info("=" * 60)
    logger.info("STEP 3: Updating NFL injuries (ESPN)...")
    logger.info("=" * 60)
    try:
        from app.database import SessionLocal
        from app.services.nfl_injuries import collect_injuries_for_upcoming_games

        db = SessionLocal()
        try:
            result = collect_injuries_for_upcoming_games(db, days_ahead=10)
            logger.info(f"Injuries: {result}")
            return True
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Injury update failed (continuing): {e}")
        return True


def generate_predictions():
    logger.info("=" * 60)
    logger.info("STEP 4: Generating NFL predictions...")
    logger.info("=" * 60)
    try:
        import subprocess

        result = subprocess.run(
            [sys.executable, "scripts/generate_nfl_predictions.py", "--upcoming"],
            capture_output=True,
            text=True,
            cwd=project_root,
            env=_utf8_env(),
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            logger.info("NFL predictions generated")
            return True
        logger.error(f"Prediction generation failed: {result.stderr}")
        return False
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return False


def write_suggested_bets():
    logger.info("=" * 60)
    logger.info("STEP 5: Writing NFL suggested bets...")
    logger.info("=" * 60)
    try:
        import subprocess

        result = subprocess.run(
            [sys.executable, "scripts/nfl_write_suggested_bets.py"],
            capture_output=True,
            text=True,
            cwd=project_root,
            env=_utf8_env(),
            encoding="utf-8",
            errors="replace",
        )
        logger.info(result.stdout[-2000:] if result.stdout else "")
        if result.returncode != 0:
            logger.error(result.stderr)
            return False
        return True
    except Exception as e:
        logger.error(f"Suggested bets error: {e}")
        return False


def evaluate_predictions():
    logger.info("=" * 60)
    logger.info("STEP 6: Evaluating NFL predictions...")
    logger.info("=" * 60)
    try:
        from app.services.prediction_evaluator import PredictionEvaluator
        from app.database import SessionLocal
        from app.models.prediction import Prediction
        from app.models.game import Game
        from sqlalchemy import and_, distinct

        db = SessionLocal()
        try:
            cutoff = date.today() - timedelta(days=7)
            finished = db.query(distinct(Game.game_id), Game.game_date).join(
                Prediction, Game.game_id == Prediction.game_id
            ).filter(
                Game.game_status == "finished",
                Game.game_date >= cutoff,
                Game.sport == "NFL",
                Prediction.actual_result.is_(None),
                Prediction.bet_type != "pass",
            ).order_by(Game.game_date.desc()).all()

            if not finished:
                logger.info("No finished NFL games with unevaluated predictions")
                return True

            evaluator = PredictionEvaluator(db)
            for game_id, _ in finished:
                try:
                    evaluator.evaluate_game(game_id)
                    db.commit()
                except Exception as e:
                    logger.warning(f"Evaluate game {game_id}: {e}")
                    db.rollback()
            return True
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Evaluation error: {e}")
        return False


def main():
    logger.info("NFL Betting Analytics - Full Update")
    logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    steps = [
        ("NFL Schedules", update_schedules),
        ("NFL Game Results", update_game_results),
        ("NFL Injuries", update_injuries),
        ("NFL Predictions", generate_predictions),
        ("NFL Suggested Bets", write_suggested_bets),
        ("NFL Evaluate Predictions", evaluate_predictions),
    ]
    results = {}
    for name, fn in steps:
        try:
            results[name] = fn()
        except Exception as e:
            logger.error(f"Exception in {name}: {e}")
            results[name] = False

    logger.info("=" * 60)
    logger.info("NFL UPDATE SUMMARY")
    logger.info("=" * 60)
    all_ok = True
    for name, ok in results.items():
        logger.info(f"  {name}: {'OK' if ok else 'FAILED'}")
        if not ok:
            all_ok = False
    logger.info(f"Overall: {'SUCCESS' if all_ok else 'FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
