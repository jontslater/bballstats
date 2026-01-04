#!/usr/bin/env python3
"""
Simple master script to update all NBA betting analytics data.

Usage:
    python scripts/update_all.py
    
This script will:
1. Update game results (previous day)
2. Update player statistics
3. Update game schedules
4. Recalculate analytics (team defense, matchups)
5. Update injury data
6. Regenerate predictions for upcoming games
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
        logging.FileHandler('update_log.txt'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def update_game_results():
    """Update previous day's game results."""
    logger.info("=" * 60)
    logger.info("STEP 1: Updating game results...")
    logger.info("=" * 60)
    
    try:
        # Import your game results collection script
        from scripts.collect_game_results import collect_previous_day_games
        
        collect_previous_day_games()  # Uses yesterday by default
        
        logger.info("✅ Game results updated")
        return True
            
    except ImportError:
        logger.warning("⚠️  Game results collection not implemented yet")
        return True  # Don't fail if not implemented
    except Exception as e:
        logger.error(f"❌ Error updating game results: {e}")
        return False


def update_player_stats():
    """Update player statistics from latest games."""
    logger.info("=" * 60)
    logger.info("STEP 2: Updating player statistics...")
    logger.info("=" * 60)
    
    try:
        from scripts.update_player_stats import update_all_player_stats
        
        result = update_all_player_stats()
        
        if result['success']:
            logger.info(f"✅ Updated stats for {result['players_updated']} players")
            return True
        else:
            logger.error(f"❌ Error: {result['error']}")
            return False
            
    except ImportError:
        logger.warning("⚠️  Player stats update not implemented yet")
        return True
    except Exception as e:
        logger.error(f"❌ Error updating player stats: {e}")
        return False


def update_schedules():
    """Update upcoming game schedules."""
    logger.info("=" * 60)
    logger.info("STEP 3: Updating game schedules...")
    logger.info("=" * 60)
    
    try:
        from scripts.collect_schedules import update_upcoming_schedules
        from scripts.create_games_from_schedules import create_games_from_schedules
        
        # First, collect schedules from NBA API
        result = update_upcoming_schedules(days_ahead=7)
        
        if not result['success']:
            logger.error(f"❌ Error collecting schedules: {result.get('error', 'Unknown error')}")
            return False
        
        logger.info(f"✅ Collected {result['games_added']} upcoming schedules")
        
        # Then, create Game records from schedules
        game_result = create_games_from_schedules(days_ahead=7)
        
        if game_result['success']:
            logger.info(f"✅ Created {game_result['created']} Game records from schedules")
            return True
        else:
            logger.error(f"❌ Error creating games: {game_result.get('error', 'Unknown error')}")
            return False
            
    except ImportError as e:
        logger.warning(f"⚠️  Schedule update not fully implemented: {e}")
        return True
    except Exception as e:
        logger.error(f"❌ Error updating schedules: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def recalculate_analytics():
    """Recalculate all analytics (team defense, matchups, etc.)."""
    logger.info("=" * 60)
    logger.info("STEP 4: Recalculating analytics...")
    logger.info("=" * 60)
    
    try:
        from app.services.analytics_service import AnalyticsService
        from app.database import SessionLocal
        
        db = SessionLocal()
        try:
            service = AnalyticsService(db)
            results = service.recalculate_all()
            logger.info("✅ Analytics recalculated successfully")
            logger.info(f"   - Team defense: {results.get('team_defense', {}).get('created', 0) + results.get('team_defense', {}).get('updated', 0)} records")
            logger.info(f"   - Matchups: {results.get('matchups', {}).get('created', 0) + results.get('matchups', {}).get('updated', 0)} records")
            logger.info(f"   - Pace: {results.get('pace', {}).get('teams_calculated', 0)} teams")
            return True
        finally:
            db.close()
            
    except ImportError:
        logger.warning("⚠️  Analytics recalculation not implemented yet")
        return True
    except Exception as e:
        logger.error(f"❌ Error recalculating analytics: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def update_injuries():
    """Update injury data."""
    logger.info("=" * 60)
    logger.info("STEP 5: Updating injury data...")
    logger.info("=" * 60)
    
    try:
        from app.scrapers.injury_scraper import InjuryScraper
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        
        scraper = InjuryScraper()
        try:
            # Use ThreadPoolExecutor for timeout (works cross-platform)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(scraper.collect_all_injuries)
                try:
                    results = future.result(timeout=300)  # 5 minute timeout
                    logger.info(f"✅ Collected {results['total']} injury reports")
                    logger.info(f"   - ESPN: {results.get('espn', 0)}")
                    logger.info(f"   - Rotowire: {results.get('rotowire', 0)}")
                    return True
                except FutureTimeoutError:
                    logger.warning("⚠️  Injury collection timed out after 5 minutes (continuing anyway)")
                    return True
        finally:
            scraper.close()
            
    except ImportError:
        logger.warning("⚠️  Injury scraper not fully implemented yet")
        return True
    except Exception as e:
        logger.warning(f"⚠️  Error updating injuries: {e} (continuing anyway)")
        import traceback
        logger.debug(traceback.format_exc())
        return True  # Don't fail on injuries


def update_lineups():
    """Update lineup confirmations."""
    logger.info("=" * 60)
    logger.info("STEP 6: Updating lineup confirmations...")
    logger.info("=" * 60)
    
    try:
        from app.scrapers.lineup_scraper import LineupScraper
        from datetime import date, timedelta
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        
        scraper = LineupScraper()
        try:
            # Collect lineups for today and tomorrow with timeout
            today = date.today()
            tomorrow = today + timedelta(days=1)
            
            def collect_lineups():
                logger.info(f"Collecting lineups for {today}...")
                results_today = scraper.collect_lineups_for_date(today)
                
                logger.info(f"Collecting lineups for {tomorrow}...")
                results_tomorrow = scraper.collect_lineups_for_date(tomorrow)
                
                return results_today, results_tomorrow
            
            # Use ThreadPoolExecutor for timeout (works cross-platform)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(collect_lineups)
                try:
                    results_today, results_tomorrow = future.result(timeout=300)  # 5 minute timeout
                    
                    total = results_today['total'] + results_tomorrow['total']
                    logger.info(f"✅ Collected {total} lineup confirmations")
                    logger.info(f"   - Today: {results_today['total']} (inferred: {results_today.get('inferred', 0)})")
                    logger.info(f"   - Tomorrow: {results_tomorrow['total']} (inferred: {results_tomorrow.get('inferred', 0)})")
                    return True
                except FutureTimeoutError:
                    logger.warning("⚠️  Lineup collection timed out after 5 minutes (continuing anyway)")
                    return True
        finally:
            scraper.close()
            
    except ImportError:
        logger.warning("⚠️  Lineup scraper not fully implemented yet")
        return True
    except Exception as e:
        logger.warning(f"⚠️  Error updating lineups: {e} (continuing anyway)")
        import traceback
        logger.debug(traceback.format_exc())
        return True  # Don't fail on lineups


def update_game_statuses():
    """Update game statuses for past games."""
    logger.info("=" * 60)
    logger.info("STEP 6.5: Updating game statuses...")
    logger.info("=" * 60)
    
    try:
        from scripts.update_game_statuses import update_game_statuses
        
        result = update_game_statuses()
        
        if result['success']:
            logger.info(f"✅ Updated {result['games_updated']} game statuses")
            return True
        else:
            logger.error(f"❌ Error: {result.get('error', 'Unknown error')}")
            return False
            
    except ImportError:
        logger.warning("⚠️  Game status update not implemented yet")
        return True
    except Exception as e:
        logger.error(f"❌ Error updating game statuses: {e}")
        return False


def sync_player_teams():
    """Sync player team assignments from recent game stats."""
    logger.info("=" * 60)
    logger.info("STEP 6.6: Syncing player team assignments...")
    logger.info("=" * 60)
    
    try:
        from app.database import SessionLocal
        from app.services.player_team_sync import PlayerTeamSyncService
        
        db = SessionLocal()
        try:
            service = PlayerTeamSyncService(db)
            result = service.sync_all_players(days_back=30)
            logger.info(f"✅ Synced {result['updated']} players, {result['unchanged']} unchanged, {result['errors']} errors")
            return True
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ Error syncing player teams: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def regenerate_predictions():
    """Regenerate predictions for upcoming games."""
    logger.info("=" * 60)
    logger.info("STEP 7: Regenerating predictions...")
    logger.info("=" * 60)
    
    try:
        from app.services.prediction_service import PredictionService
        from app.database import SessionLocal
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        
        db = SessionLocal()
        try:
            service = PredictionService(db)
            
            # Add progress callback for logging
            def progress_callback(progress_info):
                logger.info(f"   {progress_info.get('message', 'Processing...')}")
            
            # Use ThreadPoolExecutor for timeout (works cross-platform)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    service.generate_predictions_for_upcoming_games,
                    days_ahead=1,
                    progress_callback=progress_callback
                )
                try:
                    logger.info("Starting prediction generation (this may take a few minutes)...")
                    results = future.result(timeout=1800)  # 30 minute timeout
                    logger.info(f"✅ Generated predictions for {results['games_processed']} games")
                    logger.info(f"   Created: {results['created']}, Updated: {results['updated']}")
                    return True
                except FutureTimeoutError:
                    logger.warning("⚠️  Prediction generation timed out after 30 minutes (continuing anyway)")
                    return True
        finally:
            db.close()
            
    except ImportError:
        logger.warning("⚠️  Prediction generation not implemented yet")
        return True
    except Exception as e:
        logger.error(f"❌ Error generating predictions: {e}")
        import traceback
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        return False


def evaluate_predictions():
    """Evaluate predictions for finished games."""
    logger.info("=" * 60)
    logger.info("STEP 8: Evaluating predictions for finished games...")
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
            # Find finished games with unevaluated predictions (last 7 days)
            cutoff_date = date.today() - timedelta(days=7)
            
            finished_games = db.query(distinct(Game.game_id), Game.game_date).join(
                Prediction, Game.game_id == Prediction.game_id
            ).filter(
                and_(
                    Game.game_status == 'finished',
                    Game.game_date >= cutoff_date,
                    Prediction.actual_result.is_(None),
                    Prediction.bet_type != 'pass'
                )
            ).order_by(Game.game_date.desc()).all()
            
            if not finished_games:
                logger.info("✅ No finished games with unevaluated predictions")
                return True
            
            logger.info(f"Found {len(finished_games)} games with unevaluated predictions")
            
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
                    logger.warning(f"⚠️  Error evaluating game {game_id}: {e}")
                    db.rollback()
                    total_errors += 1
            
            logger.info(f"✅ Evaluated {games_processed} games")
            logger.info(f"   Predictions evaluated: {total_evaluated}")
            logger.info(f"   Predictions skipped: {total_skipped}")
            if total_errors > 0:
                logger.warning(f"   Errors: {total_errors}")
            
            return True
        finally:
            db.close()
            
    except ImportError:
        logger.warning("⚠️  Prediction evaluation not implemented yet")
        return True
    except Exception as e:
        logger.warning(f"⚠️  Error evaluating predictions: {e} (continuing anyway)")
        return True  # Don't fail on evaluation


def main():
    """Run all update steps."""
    logger.info("")
    logger.info("🏀 NBA Betting Analytics - Full Update")
    logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    
    steps = [
        ("Game Results", update_game_results),
        ("Player Stats", update_player_stats),
        ("Schedules", update_schedules),
        ("Game Statuses", update_game_statuses),  # Mark past games as finished
        ("Sync Player Teams", sync_player_teams),  # Sync team assignments from game stats
        ("Analytics", recalculate_analytics),
        ("Injuries", update_injuries),
        ("Lineups", update_lineups),
        ("Predictions", regenerate_predictions),  # Automatically generates predictions
        ("Evaluate Predictions", evaluate_predictions),  # Evaluate finished games
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
    logger.info("UPDATE SUMMARY")
    logger.info("=" * 60)
    
    for step_name, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"{step_name:20s} {status}")
    
    logger.info("")
    logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    
    # Exit code
    all_success = all(results.values())
    if all_success:
        logger.info("🎉 All updates completed successfully!")
        return 0
    else:
        logger.warning("⚠️  Some updates failed. Check logs above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

