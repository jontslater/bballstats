#!/usr/bin/env python3
"""
NBA master update script (mirrors mlb_update_all.py).
"""
import logging
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("nba_update_log.txt"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def update_game_results():
    logger.info("STEP 1: NBA game results (lookback 1 day)...")
    import subprocess

    env = {**dict(__import__("os").environ), "PYTHONUTF8": "1"}
    r = subprocess.run(
        [sys.executable, "scripts/nba_collect_game_results.py", "--lookback-days", "1"],
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        logger.error(r.stderr)
        return False
    return True


def sync_rosters():
    logger.info("STEP 2: Sync NBA rosters from ESPN...")
    from app.database import SessionLocal
    from app.services.nba_roster_sync import sync_nba_rosters_from_espn

    db = SessionLocal()
    try:
        result = sync_nba_rosters_from_espn(db)
        logger.info(f"Rosters: created={result['created']}, updated={result['updated']}, errors={result['errors']}")
        return True
    finally:
        db.close()


def update_schedules():
    logger.info("STEP 3: NBA schedules...")
    import subprocess

    env = {**dict(__import__("os").environ), "PYTHONUTF8": "1"}
    r = subprocess.run(
        [sys.executable, "scripts/nba_collect_schedule.py", "--days", "7", "--lookback-days", "1"],
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        logger.error(r.stderr)
        return False
    from scripts.create_games_from_schedules import create_games_from_schedules

    gr = create_games_from_schedules(days_ahead=7, sport="NBA")
    if not gr.get("success"):
        logger.error(gr.get("error"))
        return False
    return True


def load_calibration_gates():
    logger.info("STEP 4: Load persisted NBA calibration gates (recompute if stale)...")
    from app.database import SessionLocal
    from app.services.nba_prop_calibration import load_prop_gates

    db = SessionLocal()
    try:
        gates = load_prop_gates(db)
        logger.info(f"Calibration gates: {gates}")
        return True
    finally:
        db.close()


def generate_predictions():
    logger.info("STEP 5: NBA predictions...")
    import subprocess

    env = {**dict(__import__("os").environ), "PYTHONUTF8": "1"}
    r = subprocess.run(
        [
            sys.executable,
            "scripts/generate_predictions.py",
            "--days",
            "1",
            "--stat-types",
            "points,rebounds,assists,three_pointers_made,pts+ast+reb",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    return r.returncode == 0


def evaluate_predictions():
    logger.info("STEP 6: Evaluate NBA predictions...")
    from sqlalchemy import distinct

    from app.database import SessionLocal
    from app.models.game import Game
    from app.models.prediction import Prediction
    from app.services.prediction_evaluator import PredictionEvaluator

    db = SessionLocal()
    try:
        cutoff = date.today() - timedelta(days=7)
        finished = (
            db.query(distinct(Game.game_id), Game.game_date)
            .join(Prediction, Game.game_id == Prediction.game_id)
            .filter(
                Game.game_status == "finished",
                Game.game_date >= cutoff,
                Game.sport == "NBA",
                Prediction.actual_result.is_(None),
                Prediction.bet_type != "pass",
            )
            .order_by(Game.game_date.desc())
            .all()
        )
        ev = PredictionEvaluator(db)
        for game_id, _ in finished:
            try:
                ev.evaluate_game(game_id)
                db.commit()
            except Exception as e:
                logger.warning(f"eval {game_id}: {e}")
                db.rollback()
        return True
    finally:
        db.close()


def log_suggested_bets():
    logger.info("STEP 7: Suggested bets (uses loaded gates)...")
    from app.database import SessionLocal
    from app.services.nba_prop_calibration import load_prop_gates
    from app.services.suggested_bets import SuggestedBetsService

    db = SessionLocal()
    try:
        load_prop_gates(db)
        svc = SuggestedBetsService(db, sport="NBA")
        bets = svc.get_suggested_bets(game_date=date.today(), limit=25)
        logger.info(f"Suggested bets for today: {len(bets)}")
        return True
    finally:
        db.close()


def main():
    steps = [
        ("NBA Results", update_game_results),
        ("NBA Rosters", sync_rosters),
        ("NBA Schedules", update_schedules),
        ("NBA Calibration Gates", load_calibration_gates),
        ("NBA Predictions", generate_predictions),
        ("NBA Evaluate", evaluate_predictions),
        ("NBA Suggestions", log_suggested_bets),
    ]
    results = {}
    for name, fn in steps:
        try:
            results[name] = fn()
        except Exception as e:
            logger.exception(e)
            results[name] = False
    logger.info("SUMMARY: " + ", ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
