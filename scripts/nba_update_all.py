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
    logger.info("STEP 1: NBA game results (lookback 1 day + season missing backfill)...")
    import subprocess

    env = {**dict(__import__("os").environ), "PYTHONUTF8": "1"}
    for args in (
        ["scripts/nba_collect_game_results.py", "--lookback-days", "1"],
        ["scripts/nba_collect_game_results.py", "--backfill-season-missing"],
    ):
        r = subprocess.run(
            [sys.executable, *args],
            cwd=project_root,
            capture_output=True,
            text=True,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
        if r.stdout:
            logger.info(r.stdout.strip())
        if r.stderr:
            logger.info(r.stderr.strip())
        if r.returncode != 0:
            logger.error(r.stderr or r.stdout)
            return False
    return True


def refresh_game_results_after_schedule():
    """Second pass: box scores for games marked final during schedule sync."""
    logger.info("STEP 3b: NBA results refresh (finished games missing box scores)...")
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


def load_betting_lines(with_lines: bool):
    if not with_lines:
        return True
    logger.info("STEP: Load NBA player prop lines (The Odds API)...")
    import subprocess

    env = {**dict(__import__("os").environ), "PYTHONUTF8": "1"}
    r = subprocess.run(
        [
            sys.executable,
            "scripts/nba_load_betting_lines.py",
            "--predictions-only",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    if r.stdout:
        logger.info(r.stdout.strip())
    if r.stderr:
        logger.info(r.stderr.strip())
    if r.returncode != 0:
        logger.error(r.stderr or "nba_load_betting_lines failed")
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


def dedupe_prediction_rows():
    logger.info("STEP 5b: Dedupe NBA prediction rows...")
    import subprocess

    env = {**dict(__import__("os").environ), "PYTHONUTF8": "1"}
    r = subprocess.run(
        [sys.executable, "scripts/nba_dedupe_predictions.py"],
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    if r.stdout:
        logger.info(r.stdout.strip())
    if r.stderr:
        logger.info(r.stderr.strip())
    return r.returncode == 0


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


def generate_predictions(days_ahead: int = 0):
    logger.info("STEP 5: NBA predictions (days_ahead=%s)...", days_ahead)
    import subprocess

    from app.database import SessionLocal
    from app.services.nba_pipeline_helpers import nba_prediction_generation_ok

    env = {**dict(__import__("os").environ), "PYTHONUTF8": "1"}
    r = subprocess.run(
        [
            sys.executable,
            "scripts/generate_predictions.py",
            "--days",
            str(days_ahead),
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
    if r.stdout:
        logger.info(r.stdout.strip())
    if r.stderr:
        logger.info(r.stderr.strip())
    if r.returncode != 0:
        logger.error("generate_predictions failed")
        return False

    created = updated = 0
    import re

    for line in (r.stdout or "").splitlines():
        m = re.search(r"Created:\s*(\d+)", line)
        if m:
            created = int(m.group(1))
        m = re.search(r"Updated:\s*(\d+)", line)
        if m and "Created:" in line:
            updated = int(m.group(1))
        m = re.search(r"Created (\d+), Updated (\d+)", line)
        if m:
            created += int(m.group(1))
            updated += int(m.group(2))

    db = SessionLocal()
    try:
        ok, msg = nba_prediction_generation_ok(
            db, days_ahead=days_ahead, created=created, updated=updated
        )
        if not ok:
            logger.error(f"NBA predictions check failed: {msg}")
            return False
        logger.info(f"NBA predictions check: {msg}")
        return True
    finally:
        db.close()


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
    import argparse

    parser = argparse.ArgumentParser(description="Run full NBA data refresh pipeline")
    parser.add_argument(
        "--with-lines",
        action="store_true",
        help="After predictions, ingest FanDuel/DraftKings player prop lines via The Odds API.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="Prediction window: 0 = today only, 1 = today+tomorrow, etc. (default: 0)",
    )
    args = parser.parse_args()

    steps = [
        ("NBA Results", update_game_results),
        ("NBA Rosters", sync_rosters),
        ("NBA Schedules", update_schedules),
        ("NBA Results Refresh", refresh_game_results_after_schedule),
        ("NBA Calibration Gates", load_calibration_gates),
        ("NBA Predictions", lambda: generate_predictions(args.days)),
        ("NBA Dedupe Predictions", dedupe_prediction_rows),
        ("NBA Betting Lines", lambda: load_betting_lines(args.with_lines)),
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
