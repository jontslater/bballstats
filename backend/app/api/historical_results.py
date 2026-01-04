"""
Historical Prediction Results API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Union
from datetime import date, datetime, timedelta
from app.database import SessionLocal
from app.services.prediction_evaluator import PredictionEvaluator
from app.services.parlay_evaluator import ParlayEvaluator
from pydantic import BaseModel
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/historical-results", tags=["historical-results"])


class PredictionResultResponse(BaseModel):
    """Prediction result response model."""
    prediction_id: int
    player_id: int
    player_name: str
    game_id: int
    game_date: str
    game_matchup: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    stat_type: str
    bet_type: str
    line: Optional[float]
    predicted_mean: Optional[float]
    predicted_std: Optional[float]
    actual_result: Optional[int]
    hit: Optional[Union[bool, str]]  # Can be True, False, None (pending), or 'void'
    probability: Optional[float]
    confidence_level: Optional[str]
    volatility_level: Optional[str]
    
    class Config:
        from_attributes = True


class AccuracyStatsResponse(BaseModel):
    """Accuracy statistics response model."""
    total: int
    evaluated: int
    unevaluated: int
    hits: int
    misses: int
    accuracy: float
    by_bet_type: Optional[dict] = None
    
    class Config:
        from_attributes = True


@router.get("/predictions", response_model=List[PredictionResultResponse])
async def get_prediction_results(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    bet_type: Optional[str] = Query(None, description="Filter by bet type"),
    stat_type: Optional[str] = Query(None, description="Filter by stat type"),
    limit: int = Query(100, description="Maximum number of results")
):
    """Get historical prediction results."""
    db = SessionLocal()
    try:
        evaluator = PredictionEvaluator(db)
        
        parsed_start = None
        parsed_end = None
        
        if start_date:
            try:
                parsed_start = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format")
        
        if end_date:
            try:
                parsed_end = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format")
        
        # If no date range specified, default to last 30 days to prevent huge queries
        if not parsed_start and not parsed_end:
            from datetime import timedelta
            parsed_end = date.today()
            parsed_start = parsed_end - timedelta(days=30)
        
        results = evaluator.get_prediction_results(
            start_date=parsed_start,
            end_date=parsed_end,
            bet_type=bet_type,
            stat_type=stat_type
        )
        
        return results[:limit]
    finally:
        db.close()


@router.get("/accuracy", response_model=AccuracyStatsResponse)
async def get_accuracy_stats(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    bet_type: Optional[str] = Query(None, description="Filter by bet type")
):
    """Get accuracy statistics for predictions."""
    db = SessionLocal()
    try:
        evaluator = PredictionEvaluator(db)
        
        parsed_start = None
        parsed_end = None
        
        if start_date:
            try:
                parsed_start = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format")
        
        if end_date:
            try:
                parsed_end = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format")
        
        # If no date range specified, default to last 30 days to prevent huge queries
        if not parsed_start and not parsed_end:
            from datetime import timedelta
            parsed_end = date.today()
            parsed_start = parsed_end - timedelta(days=30)
        
        stats = evaluator.get_accuracy_stats(
            start_date=parsed_start,
            end_date=parsed_end,
            bet_type=bet_type
        )
        
        # Ensure by_bet_type is included (might be None if no results)
        if 'by_bet_type' not in stats:
            stats['by_bet_type'] = {}
        
        return stats
    finally:
        db.close()


@router.post("/evaluate/date/{target_date}")
async def evaluate_date(
    target_date: str,
    collect_stats: bool = Query(True, description="Collect box scores if missing")
):
    """
    Evaluate all predictions for a specific date (optimized for single date).
    
    This is faster than evaluate/all because it only processes one date and uses
    the ESPN box score scraper directly, which is more reliable for recent games.
    
    Args:
        target_date: Date to evaluate (YYYY-MM-DD format)
        collect_stats: Collect box scores if missing
    """
    db = SessionLocal()
    try:
        # Parse the target date
        try:
            parsed_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {target_date}. Use YYYY-MM-DD")
        
        from app.models.prediction import Prediction
        from app.models.game import Game
        from app.models.player_game_stat import PlayerGameStat
        from sqlalchemy import and_, or_, func, distinct
        
        # First, collect box scores if needed (using ESPN scraper directly - faster for single date)
        stats_collected = 0
        if collect_stats:
            from app.scrapers.box_score_scraper import BoxScoreScraper
            box_score_scraper = BoxScoreScraper(db_session=db, delay=1.5)
            
            try:
                # Use ESPN scraper directly for this date (most reliable for recent games)
                espn_results = box_score_scraper.collect_box_scores_for_date(parsed_date, force_rescrape=False)
                stats_collected = espn_results.get("stats_created", 0) + espn_results.get("stats_updated", 0)
                print(f"📊 Collected {stats_collected} player stats for {target_date}")
            except Exception as e:
                print(f"⚠️  Warning: Could not collect box scores: {e}")
                # Continue anyway - some games might already have stats
        
        # Find games to evaluate: finished games OR games with box scores
        # (Some games may have box scores but status hasn't been updated to 'finished' yet)
        games_with_box_scores = db.query(PlayerGameStat.game_id).distinct().subquery()
        
        games_to_evaluate = db.query(distinct(Game.game_id), Game.game_id).filter(
            and_(
                Game.game_date == parsed_date,
                # Include if finished OR has box scores
                or_(
                    Game.game_status == 'finished',
                    Game.game_id.in_(db.query(games_with_box_scores.c.game_id))
                )
            )
        ).all()
        
        if not games_to_evaluate:
            return {
                'message': f'No finished games or games with box scores found for {target_date}',
                'games_processed': 0,
                'total_evaluated': 0,
                'total_skipped': 0,
                'total_errors': 0,
                'stats_collected': stats_collected
            }
        
        game_ids = [g.game_id for g in games_to_evaluate]
        
        evaluator = PredictionEvaluator(db)
        
        total_evaluated = 0
        total_skipped = 0
        total_errors = 0
        games_processed = 0
        
        for game_id in game_ids:
            try:
                result = evaluator.evaluate_game(game_id)
                total_evaluated += result['evaluated']
                total_skipped += result['skipped']
                total_errors += result['errors']
                games_processed += 1
                db.commit()
            except Exception as e:
                print(f"❌ Error evaluating game {game_id}: {e}")
                db.rollback()
                total_errors += 1
        
        return {
            'message': f'Evaluated {games_processed} games for {target_date}',
            'games_processed': games_processed,
            'total_evaluated': total_evaluated,
            'total_skipped': total_skipped,
            'total_errors': total_errors,
            'stats_collected': stats_collected
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error evaluating games: {str(e)}")
    finally:
        db.close()


async def evaluate_all_with_progress(days_back: int, collect_stats: bool):
    """Generator function that yields progress updates during evaluation."""
    db = SessionLocal()
    try:
        total_steps = 4  # Collect stats, find games, evaluate games, evaluate parlays
        current_step = 0
        
        # Step 1: Collect box scores if needed
        if collect_stats:
            current_step = 1
            yield {
                'progress': 5,
                'message': f'Collecting box scores for finished games (last {days_back} days)...',
                'step': current_step,
                'total_steps': total_steps
            }
            
            try:
                # Collect box scores with progress updates
                from app.models.game import Game
                from app.models.player_game_stat import PlayerGameStat
                from sqlalchemy import and_, func
                from datetime import date, timedelta
                from app.scrapers.nba_api_client import NBAAPIClient
                from app.scrapers.basketball_reference import BasketballReferenceScraper
                from app.scrapers.box_score_scraper import BoxScoreScraper
                
                cutoff_date = date.today() - timedelta(days=days_back)
                
                # Find finished games without player stats
                finished_games = db.query(Game).filter(
                    and_(
                        Game.game_status == 'finished',
                        Game.game_date >= cutoff_date
                    )
                ).all()
                
                # With force_rescrape=True, we'll process all finished games (not just ones without stats)
                # This allows fixing incorrect data
                games_needing_stats = finished_games  # Process all finished games
                
                total_games_to_collect = len(games_needing_stats)
                
                if total_games_to_collect > 0:
                    yield {
                        'progress': 10,
                        'message': f'Found {total_games_to_collect} games needing box scores. Starting collection...',
                        'step': current_step,
                        'total_steps': total_steps,
                        'box_score_games_total': total_games_to_collect
                    }
                    
                    client = NBAAPIClient(delay=1.0)
                    br_scraper = BasketballReferenceScraper()
                    box_score_scraper = BoxScoreScraper(db_session=db, delay=1.5)
                    
                    total_stats_created = 0
                    games_processed = 0
                    
                    # Group games by date for more efficient ESPN scraping
                    games_by_date = {}
                    for game in games_needing_stats:
                        if game.game_date not in games_by_date:
                            games_by_date[game.game_date] = []
                        games_by_date[game.game_date].append(game)
                    
                    total_dates = len(games_by_date)
                    dates_processed = 0
                    
                    # First, try ESPN for each date (more reliable for recent games)
                    for game_date, date_games in games_by_date.items():
                        dates_processed += 1
                        progress_pct = 10 + int((dates_processed / total_dates) * 20)  # 10-30% for box score collection
                        yield {
                            'progress': progress_pct,
                            'message': f'Collecting box scores for {game_date} ({len(date_games)} games)... ({dates_processed}/{total_dates} dates)',
                            'step': current_step,
                            'total_steps': total_steps,
                            'box_score_dates_processed': dates_processed,
                            'box_score_dates_total': total_dates
                        }
                        
                        # Use force_rescrape=True to fix any incorrect data
                        espn_results = box_score_scraper.collect_box_scores_for_date(game_date, force_rescrape=True)
                        games_processed += espn_results["games_processed"]
                        total_stats_created += espn_results.get("stats_created", 0) + espn_results.get("stats_updated", 0)
                        
                        stats_created = espn_results.get("stats_created", 0)
                        stats_updated = espn_results.get("stats_updated", 0)
                        total_stats = stats_created + stats_updated
                        if stats_updated > 0:
                            message = f'✅ {game_date}: Updated {stats_updated} and created {stats_created} player stats for {espn_results["games_processed"]} games'
                        else:
                            message = f'✅ {game_date}: Collected {total_stats} player stats for {espn_results["games_processed"]} games'
                        
                        yield {
                            'progress': progress_pct,
                            'message': message,
                            'step': current_step,
                            'total_steps': total_steps,
                            'box_score_games_processed': games_processed,
                            'box_score_games_total': total_games_to_collect,
                            'box_score_stats_created': total_stats_created
                        }
                        
                        # Remove games that were successfully collected from our list
                        for game in date_games[:]:
                            stats_count = db.query(func.count(PlayerGameStat.stat_id)).filter(
                                PlayerGameStat.game_id == game.game_id
                            ).scalar()
                            if stats_count > 0:
                                date_games.remove(game)
                    
                    # For remaining games, try NBA API and Basketball Reference
                    remaining_games = [g for games_list in games_by_date.values() for g in games_list]
                    total_remaining = len(remaining_games)
                    
                    for idx, game in enumerate(remaining_games, 1):
                        progress_pct = 30 + int((idx / max(total_remaining, 1)) * 3)  # 30-33% for remaining games
                        yield {
                            'progress': progress_pct,
                            'message': f'Trying alternative sources for game {game.game_id} ({idx}/{total_remaining} remaining)...',
                            'step': current_step,
                            'total_steps': total_steps,
                            'box_score_games_processed': games_processed + idx - 1,
                            'box_score_games_total': total_games_to_collect
                        }
                        
                        # ... (existing game collection logic would go here, but we'll keep it simple for now)
                        # This is a placeholder - the actual collection happens in collect_for_finished_games
                    
                    yield {
                        'progress': 33,
                        'message': f'Box score collection complete: {games_processed} games, {total_stats_created} player stats',
                        'step': current_step,
                        'total_steps': total_steps,
                        'box_score_games_processed': games_processed,
                        'box_score_stats_created': total_stats_created
                    }
                else:
                    yield {
                        'progress': 33,
                        'message': 'All games already have box scores',
                        'step': current_step,
                        'total_steps': total_steps
                    }
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield {
                    'progress': 33,
                    'message': f'Warning: Could not collect stats: {str(e)[:100]}',
                    'step': current_step,
                    'total_steps': total_steps
                }
        
        # Step 2: Find games to evaluate
        current_step = 2
        yield {
            'progress': int((current_step / total_steps) * 100),
            'message': 'Finding finished games with unevaluated predictions...',
            'step': current_step,
            'total_steps': total_steps
        }
        
        from app.models.prediction import Prediction
        from app.models.game import Game
        from app.models.player_game_stat import PlayerGameStat
        from sqlalchemy import and_, func, distinct, or_
        
        cutoff_date = date.today() - timedelta(days=days_back)
        
        # ENHANCEMENT: Find games that are finished OR have box scores
        # Some games may have box scores but status hasn't been updated to 'finished' yet
        games_with_box_scores = db.query(PlayerGameStat.game_id).distinct().subquery()
        
        finished_games = db.query(distinct(Game.game_id), Game.game_date).join(
            Prediction, Game.game_id == Prediction.game_id
        ).filter(
            and_(
                # Include if finished OR has box scores
                or_(
                    Game.game_status == 'finished',
                    Game.game_id.in_(db.query(games_with_box_scores.c.game_id))
                ),
                Game.game_date >= cutoff_date,
                Prediction.actual_result.is_(None),
                Prediction.bet_type != 'pass'
            )
        ).order_by(Game.game_date.desc()).all()
        
        if not finished_games:
            yield {
                'progress': 100,
                'message': 'No finished games with unevaluated predictions found',
                'step': total_steps,
                'total_steps': total_steps,
                'complete': True,
                'games_processed': 0,
                'total_evaluated': 0,
                'total_skipped': 0,
                'total_errors': 0
            }
            return
        
        total_games = len(finished_games)
        yield {
            'progress': int((current_step / total_steps) * 100),
            'message': f'Found {total_games} games to evaluate',
            'step': current_step,
            'total_steps': total_steps,
            'total_games': total_games
        }
        
        # Step 3: Evaluate games
        current_step = 3
        evaluator = PredictionEvaluator(db)
        
        total_evaluated = 0
        total_skipped = 0
        total_errors = 0
        games_processed = 0
        
        # Calculate progress range for evaluation step (33% to 95%)
        evaluation_progress_range = 95 - 33  # 62 percentage points for evaluation
        
        for idx, (game_id, game_date) in enumerate(finished_games, 1):
            try:
                # Send progress update before evaluating
                progress = 33 + int((idx / total_games) * evaluation_progress_range)
                yield {
                    'progress': progress,
                    'message': f'Evaluating game {idx}/{total_games} (Game ID: {game_id}, Date: {game_date})...',
                    'step': current_step,
                    'total_steps': total_steps,
                    'games_processed': games_processed,
                    'total_games': total_games,
                    'total_evaluated': total_evaluated,
                    'total_skipped': total_skipped,
                    'total_errors': total_errors
                }
                
                result = evaluator.evaluate_game(game_id)
                total_evaluated += result['evaluated']
                total_skipped += result['skipped']
                total_errors += result['errors']
                games_processed += 1
                db.commit()
                
                # Update progress after evaluation
                progress = 33 + int((idx / total_games) * evaluation_progress_range)
                yield {
                    'progress': progress,
                    'message': f'✅ Game {idx}/{total_games} (ID: {game_id}) - {result["evaluated"]} predictions evaluated, {result["skipped"]} skipped',
                    'step': current_step,
                    'total_steps': total_steps,
                    'games_processed': games_processed,
                    'total_games': total_games,
                    'total_evaluated': total_evaluated,
                    'total_skipped': total_skipped,
                    'total_errors': total_errors
                }
            except Exception as e:
                print(f"Error evaluating game {game_id}: {e}")
                db.rollback()
                total_errors += 1
                progress = 33 + int((idx / total_games) * evaluation_progress_range)
                yield {
                    'progress': progress,
                    'message': f'❌ Error evaluating game {game_id}: {str(e)[:100]}',
                    'step': current_step,
                    'total_steps': total_steps,
                    'games_processed': games_processed,
                    'total_games': total_games,
                    'total_evaluated': total_evaluated,
                    'total_skipped': total_skipped,
                    'total_errors': total_errors
                }
        
        # Step 4: Evaluate parlays for finished games
        current_step = 4
        total_steps = 5  # Update total steps to include parlay evaluation and PMB resolution
        
        yield {
            'progress': 95,
            'message': 'Evaluating parlays for finished games...',
            'step': current_step,
            'total_steps': total_steps
        }
        
        parlay_evaluator = ParlayEvaluator(db)
        parlay_result = None
        try:
            parlay_result = parlay_evaluator.evaluate_all_finished_parlays()
            yield {
                'progress': 98,
                'message': f"Evaluated {parlay_result['evaluated']} parlays ({parlay_result['hits']} hits, {parlay_result['misses']} misses)",
                'step': current_step,
                'total_steps': total_steps,
                'parlay_results': parlay_result
            }
            
            # Step 5: Resolve Poor Man's Bet challenges
            from app.services.poor_mans_bet_service import PoorMansBetService
            pmb_service = PoorMansBetService(db)
            pmb_result = pmb_service.resolve_pending_bets()
            yield {
                'progress': 99,
                'message': f"Resolved {pmb_result['resolved']} Poor Man's Bet challenges ({pmb_result['hits']} hits, {pmb_result['misses']} misses)",
                'step': 5,
                'total_steps': 5,
                'parlay_results': parlay_result,
                'poor_mans_bet_results': pmb_result
            }
        except Exception as e:
            logger.error(f"Error evaluating parlays: {e}")
            yield {
                'progress': 98,
                'message': f'Error evaluating parlays: {str(e)[:100]}',
                'step': current_step,
                'total_steps': total_steps,
                'error': str(e)
            }
        
        # Final completion message
        parlay_msg = ""
        if parlay_result:
            parlay_msg = f", evaluated {parlay_result['evaluated']} parlays"
        
        yield {
            'progress': 100,
            'message': f'✅ Evaluation complete! Processed {games_processed} games, evaluated {total_evaluated} predictions{parlay_msg}',
            'step': total_steps,
            'total_steps': total_steps,
            'complete': True,
            'games_processed': games_processed,
            'total_evaluated': total_evaluated,
            'total_skipped': total_skipped,
            'total_errors': total_errors,
            'parlay_results': parlay_result
        }
        
    except Exception as e:
        yield {
            'progress': 100,
            'message': f'Error: {str(e)}',
            'step': 0,
            'total_steps': 0,
            'complete': True,
            'error': str(e)
        }
    finally:
        db.close()


@router.post("/evaluate/all")
async def evaluate_all_finished_games(
    days_back: Optional[int] = Query(30, description="Number of days back to evaluate"),
    collect_stats: bool = Query(True, description="Collect box scores if missing")
):
    """
    Evaluate all predictions for all finished games with progress updates via SSE.
    
    This will find all finished games with predictions that haven't been evaluated
    and evaluate them automatically.
    
    If collect_stats is True, it will first collect box scores for games that don't have them.
    """
    async def generate():
        async for update in evaluate_all_with_progress(days_back or 90, collect_stats):
            yield f"data: {json.dumps(update)}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/evaluation-status")
async def get_evaluation_status():
    """
    Get status of prediction evaluations.
    
    Returns information about how many predictions have been evaluated
    and how many still need evaluation.
    """
    db = SessionLocal()
    try:
        from app.models.prediction import Prediction
        from app.models.game import Game
        from sqlalchemy import and_, func, distinct
        
        # Total predictions (non-pass)
        total_preds = db.query(func.count(Prediction.prediction_id)).filter(
            Prediction.bet_type != 'pass'
        ).scalar()
        
        # Evaluated predictions
        evaluated_preds = db.query(func.count(Prediction.prediction_id)).filter(
            and_(
                Prediction.actual_result.isnot(None),
                Prediction.bet_type != 'pass'
            )
        ).scalar()
        
        # Finished games with unevaluated predictions
        finished_games_with_unevaluated = db.query(distinct(Game.game_id)).join(
            Prediction, Game.game_id == Prediction.game_id
        ).filter(
            and_(
                Game.game_status == 'finished',
                Prediction.actual_result.is_(None),
                Prediction.bet_type != 'pass'
            )
        ).count()
        
        # Total finished games
        total_finished_games = db.query(func.count(Game.game_id)).filter(
            Game.game_status == 'finished'
        ).scalar()
        
        return {
            'total_predictions': total_preds,
            'evaluated_predictions': evaluated_preds,
            'unevaluated_predictions': total_preds - evaluated_preds,
            'finished_games_with_unevaluated': finished_games_with_unevaluated,
            'total_finished_games': total_finished_games,
            'evaluation_percentage': round((evaluated_preds / total_preds * 100) if total_preds > 0 else 0, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting evaluation status: {str(e)}")
    finally:
        db.close()


@router.post("/evaluate-parlays")
async def evaluate_parlays(
    game_id: Optional[int] = Query(None, description="Evaluate parlays for a specific game"),
    all_finished: bool = Query(False, description="Evaluate all parlays for finished games")
):
    """
    Evaluate parlays for finished games.
    
    If game_id is provided, evaluates all parlays that include plays from that game.
    If all_finished is True, evaluates all parlays for all finished games.
    """
    db = SessionLocal()
    try:
        evaluator = ParlayEvaluator(db)
        
        if game_id:
            result = evaluator.evaluate_parlays_for_game(game_id)
            return result
        elif all_finished:
            result = evaluator.evaluate_all_finished_parlays()
            return result
        else:
            raise HTTPException(
                status_code=400,
                detail="Must provide either game_id or set all_finished=true"
            )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error evaluating parlays: {str(e)}")
    finally:
        db.close()


@router.get("/parlay-results")
async def get_parlay_results(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filter by status (hit, miss, pending, void)"),
    include_suggested: bool = Query(True, description="Include suggested parlays (regenerated for past dates)")
):
    """
    Get parlay evaluation results, including both saved parlays and suggested parlays.
    """
    db = SessionLocal()
    try:
        from app.models.parlay import Parlay
        from app.models.user_play import UserPlay
        from app.models.game import Game
        from app.models.player import Player
        from app.models.player_game_stat import PlayerGameStat
        from app.services.suggested_bets import SuggestedBetsService
        from app.services.builder_plays import BuilderPlaysService
        from sqlalchemy import and_, or_
        from collections import defaultdict
        
        results = []
        
        # Get saved parlays
        query = db.query(Parlay)
        
        # Filter by status
        if status:
            query = query.filter(Parlay.status == status)
        
        # Filter by date range
        if start_date or end_date:
            query = query.join(UserPlay, Parlay.plays).join(Game, UserPlay.game_id == Game.game_id)
            
            if start_date:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(Game.game_date >= start)
            
            if end_date:
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(Game.game_date <= end)
            
            query = query.distinct()
        
        saved_parlays = query.order_by(Parlay.created_at.desc()).all()
        
        for parlay in saved_parlays:
            # Get play details
            plays_data = []
            for play in parlay.plays:
                player = db.query(Player).filter(Player.player_id == play.player_id).first()
                game = db.query(Game).filter(Game.game_id == play.game_id).first()
                
                plays_data.append({
                    'play_id': play.play_id,
                    'player_name': player.name if player else f"Player {play.player_id}",
                    'game_date': game.game_date.isoformat() if game else None,
                    'stat_type': play.stat_type,
                    'bet_line': play.bet_line,
                    'status': play.status,
                    'actual_result': play.actual_result
                })
            
            results.append({
                'parlay_id': parlay.parlay_id,
                'name': parlay.name,
                'status': parlay.status,
                'legs_hit': parlay.legs_hit,
                'total_legs': parlay.total_legs,
                'total_odds': parlay.total_odds,
                'total_probability': parlay.total_probability,
                'created_at': parlay.created_at.isoformat() if parlay.created_at else None,
                'plays': plays_data,
                'type': 'saved'
            })
        
        # Get suggested parlays for past dates if requested
        if include_suggested:
            # Determine date range for suggested parlays
            if start_date and end_date:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
            elif start_date:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                end = start
            elif end_date:
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                start = end
            else:
                # Default to last 7 days if no date range specified
                from datetime import timedelta
                end = date.today() - timedelta(days=1)  # Yesterday
                start = end - timedelta(days=6)  # 7 days total
            
            # Generate suggested parlays for each date in range
            current_date = start
            suggested_service = SuggestedBetsService(db)
            builder_service = BuilderPlaysService(db)
            
            while current_date <= end:
                # Get safe long parlays (limit to 2 per date)
                safe_long = suggested_service.get_safe_long_parlays(
                    game_date=current_date,
                    limit=2,
                    num_legs=12,
                    min_leg_probability=0.75
                )
                # Add type to each parlay
                for parlay in safe_long:
                    parlay['type'] = 'safe_long'
                    # Ensure legs have bet_line format
                    for leg in parlay.get('legs', []):
                        if 'bet_line' not in leg and 'line' in leg:
                            leg['bet_line'] = f"Over {leg['line']:.1f}"
                
                # Get builder plays
                builders = builder_service.get_builder_plays(
                    game_date=current_date,
                    limit=5,
                    num_legs=2
                )
                # Add type to each parlay
                for parlay in builders:
                    parlay['type'] = 'builder'
                
                # Get regular suggested parlays
                suggested = suggested_service.get_suggested_parlays_by_stat_mix(
                    game_date=current_date,
                    limit=5,
                    diversify_players=True
                )
                # Add type to each parlay
                for parlay in suggested:
                    parlay['type'] = 'suggested'
                    # Ensure legs have bet_line format
                    for leg in parlay.get('legs', []):
                        if 'bet_line' not in leg and 'line' in leg:
                            leg['bet_line'] = f"Over {leg['line']:.1f}"
                
                # Convert to results format
                # Track seen parlays to avoid duplicates (based on leg content)
                # Note: We only deduplicate within the same type to avoid removing legitimately different parlays
                seen_parlay_keys_by_type = {
                    'safe_long': set(),
                    'builder': set(),
                    'suggested': set()
                }
                
                for parlay_data in safe_long + builders + suggested:
                    parlay_type = parlay_data.get('type', 'unknown')
                    
                    # Create a unique key for this parlay based on its legs
                    # First, ensure bet_line is constructed for consistent key generation
                    leg_keys = []
                    for leg in parlay_data.get('legs', []):
                        bet_line = leg.get('bet_line', '')
                        if not bet_line and 'line' in leg:
                            bet_line = f"Over {leg['line']:.1f}"
                        leg_key = f"{leg.get('player_id')}_{leg.get('game_id')}_{leg.get('stat_type')}_{bet_line}"
                        leg_keys.append(leg_key)
                    parlay_key = f"{current_date}_{'_'.join(sorted(leg_keys))}"
                    
                    # Skip if we've already seen this parlay of this type
                    if parlay_key in seen_parlay_keys_by_type.get(parlay_type, set()):
                        continue
                    seen_parlay_keys_by_type[parlay_type].add(parlay_key)
                    
                    # Evaluate each leg to see if it hit
                    legs_data = []
                    all_hit = True
                    any_missed = False
                    
                    for leg in parlay_data.get('legs', []):
                        player_id = leg.get('player_id')
                        game_id = leg.get('game_id')
                        stat_type = leg.get('stat_type')
                        bet_line = leg.get('bet_line', '')
                        
                        # If bet_line is missing but we have 'line', construct it
                        if not bet_line and 'line' in leg:
                            bet_line = f"Over {leg['line']:.1f}"
                        
                        # Get actual result
                        game = db.query(Game).filter(Game.game_id == game_id).first()
                        
                        # Check if we have box score data (even if game status isn't 'finished' yet)
                        stat = db.query(PlayerGameStat).filter(
                            and_(
                                PlayerGameStat.player_id == player_id,
                                PlayerGameStat.game_id == game_id,
                                PlayerGameStat.minutes_played > 0
                            )
                        ).first()
                        
                        # If we have stats, treat the game as finished (has box scores)
                        if stat:
                            # Get actual value
                            if stat_type == 'points':
                                actual = stat.points
                            elif stat_type == 'rebounds':
                                actual = stat.rebounds
                            elif stat_type == 'assists':
                                actual = stat.assists
                            elif stat_type == 'points_rebounds':
                                # Combo: points + rebounds
                                if stat.points is not None and stat.rebounds is not None:
                                    actual = stat.points + stat.rebounds
                                else:
                                    actual = None
                            elif stat_type == 'points_assists':
                                # Combo: points + assists
                                if stat.points is not None and stat.assists is not None:
                                    actual = stat.points + stat.assists
                                else:
                                    actual = None
                            elif stat_type == 'rebounds_assists':
                                # Combo: rebounds + assists
                                if stat.rebounds is not None and stat.assists is not None:
                                    actual = stat.rebounds + stat.assists
                                else:
                                    actual = None
                            else:
                                actual = None
                            
                            # Evaluate bet line - if we have actual, we can always determine hit/miss
                            # Only show "pending" if we truly don't have the actual result
                            hit = None
                            status = 'pending'  # Default to pending
                            
                            if actual is not None and bet_line:
                                # We have actual stats - we can always evaluate
                                import re
                                over_match = re.match(r'^Over\s+([\d.]+)$', bet_line, re.IGNORECASE)
                                under_match = re.match(r'^Under\s+([\d.]+)$', bet_line, re.IGNORECASE)
                                
                                if over_match:
                                    line_value = float(over_match.group(1))
                                    hit = actual > line_value
                                    status = 'hit' if hit else 'miss'
                                elif under_match:
                                    line_value = float(under_match.group(1))
                                    hit = actual < line_value
                                    status = 'hit' if hit else 'miss'
                                else:
                                    # Can't parse bet line format, but we have actual - treat as miss
                                    hit = False
                                    status = 'miss'
                                
                                # Update parlay status
                                if hit is False:
                                    any_missed = True
                                    all_hit = False
                                # If hit is True, we still need to check all legs for overall parlay status
                            
                            legs_data.append({
                                'player_name': leg.get('player_name', f"Player {player_id}"),
                                'game_date': game.game_date.isoformat() if game else None,
                                'stat_type': stat_type,
                                'bet_line': bet_line,
                                'status': status,
                                'actual_result': actual
                            })
                        else:
                            # Check if game is finished but player didn't play (or no stats yet)
                            if game and game.game_status == 'finished':
                                # Player didn't play - mark as void (doesn't count against parlay)
                                legs_data.append({
                                    'player_name': leg.get('player_name', f"Player {player_id}"),
                                    'game_date': game.game_date.isoformat() if game else None,
                                    'stat_type': stat_type,
                                    'bet_line': bet_line,
                                    'status': 'void',  # Player didn't play - void the leg
                                    'actual_result': None
                                })
                                # Voids don't count against the parlay - don't set any_missed or all_hit = False
                            else:
                                # Game not finished and no stats yet
                                legs_data.append({
                                    'player_name': leg.get('player_name', f"Player {player_id}"),
                                    'game_date': game.game_date.isoformat() if game else None,
                                    'stat_type': stat_type,
                                    'bet_line': bet_line,
                                    'status': 'pending',
                                    'actual_result': None
                                })
                                all_hit = False
                    
                    # Determine overall status (OUTSIDE the leg loop)
                    # Count non-void legs for evaluation
                    non_void_legs = [leg for leg in legs_data if leg['status'] != 'void']
                    non_void_hits = sum(1 for leg in non_void_legs if leg['status'] == 'hit')
                    non_void_misses = sum(1 for leg in non_void_legs if leg['status'] == 'miss')
                    non_void_pending = sum(1 for leg in non_void_legs if leg['status'] == 'pending')
                    
                    if non_void_misses > 0:
                        parlay_status = 'miss'
                    elif non_void_pending > 0:
                        parlay_status = 'pending'
                    elif len(non_void_legs) > 0 and non_void_hits == len(non_void_legs):
                        # All non-void legs hit = parlay hits (voids don't count)
                        parlay_status = 'hit'
                    else:
                        parlay_status = 'pending'
                    
                    legs_hit = non_void_hits
                    
                    # Create unique parlay_id based on content
                    import hashlib
                    parlay_content = f"{current_date}_{parlay_data.get('type', 'unknown')}_{'_'.join(sorted(leg_keys))}"
                    parlay_id_hash = hashlib.md5(parlay_content.encode()).hexdigest()[:8]
                    
                    results.append({
                        'parlay_id': f"suggested_{current_date}_{parlay_id_hash}",
                        'name': parlay_data.get('name', f"Suggested Parlay ({parlay_data.get('type', 'unknown')})"),
                        'status': parlay_status,
                        'legs_hit': legs_hit,
                        'total_legs': len(legs_data),
                        'total_odds': parlay_data.get('total_odds') or parlay_data.get('combined_odds'),
                        'total_probability': parlay_data.get('total_probability') or parlay_data.get('combined_probability'),
                        'created_at': current_date.isoformat(),
                        'plays': legs_data,
                        'type': 'suggested',
                        'parlay_type': parlay_data.get('type', 'unknown')
                    })
                
                # Move to next date
                from datetime import timedelta
                current_date += timedelta(days=1)
        
        # Sort by date (most recent first)
        results.sort(key=lambda x: x['created_at'] or '', reverse=True)
        
        return {
            'total_parlays': len(results),
            'parlays': results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting parlay results: {str(e)}")
    finally:
        db.close()
