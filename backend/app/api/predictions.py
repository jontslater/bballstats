"""
Prediction API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
import json
import asyncio
import logging
from app.database import SessionLocal
from app.models.prediction import Prediction
from app.models.game import Game
from app.models.player import Player
from app.services.prediction_service import PredictionService
from app.services.prediction_history_helper import get_last_n_games_for_stat
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class PredictionResponse(BaseModel):
    """Prediction response model."""
    prediction_id: int
    player_id: int
    player_name: str
    game_id: int
    stat_type: str
    distribution_mean: float
    distribution_std_dev: float
    safe_line: float
    safe_probability: float
    standard_line: float
    standard_probability: float
    long_shot_line: float
    long_shot_probability: float
    bet_type: str
    confidence_level: str
    volatility_level: str
    reasoning: Optional[str] = None
    
    class Config:
        from_attributes = True


class GeneratePredictionsRequest(BaseModel):
    """Request to generate predictions."""
    game_id: Optional[int] = None
    days_ahead: int = 1
    stat_types: List[str] = ["points", "rebounds", "assists", "three_pointers_made"]
    sport: str = "NBA"  # Sport type (NBA or NFL)


@router.get("/game/{game_id}")
async def get_predictions_for_game(
    game_id: int,
    stat_type: Optional[str] = Query(None, description="Filter by stat type"),
    bet_type: Optional[str] = Query(None, description="Filter by bet type (safe, standard, long_shot)"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get all predictions for a specific game."""
    db = SessionLocal()
    try:
        # Validate sport
        if sport not in ['NBA', 'NFL']:
            raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}. Must be 'NBA' or 'NFL'")
        
        # Verify game exists and matches sport
        game = db.query(Game).filter(
            Game.game_id == game_id,
            Game.sport == sport
        ).first()
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        query = db.query(Prediction).filter(
            Prediction.game_id == game_id,
            Prediction.sport == sport
        )
        
        if stat_type:
            query = query.filter(Prediction.stat_type == stat_type)
        
        if bet_type:
            query = query.filter(Prediction.bet_type == bet_type)
        
        predictions = query.all()
        
        # Filter out predictions for players who didn't actually play (for finished games)
        # AND filter out injured players (for upcoming games)
        from app.models.player_game_stat import PlayerGameStat
        from app.services.injury_context import InjuryContext
        injury_context = InjuryContext(db)
        
        result = []
        for pred in predictions:
            # Check if game is finished
            game = db.query(Game).filter(Game.game_id == pred.game_id).first()
            if game and game.game_status == 'finished':
                # Check if player actually played
                stat = db.query(PlayerGameStat).filter(
                    PlayerGameStat.player_id == pred.player_id,
                    PlayerGameStat.game_id == pred.game_id,
                    PlayerGameStat.minutes_played > 0
                ).first()
                # Skip predictions for players who didn't play
                if not stat:
                    continue
            elif game and game.game_status in ['scheduled', 'in_progress']:
                # For upcoming games, check injury status
                injury_status = injury_context.get_player_injury_status(pred.player_id)
                if injury_status and injury_status['status'] in ['Out', 'Doubtful', 'Questionable']:
                    continue  # Skip injured players
            player = db.query(Player).filter(Player.player_id == pred.player_id).first()
            game = db.query(Game).filter(Game.game_id == pred.game_id).first()
            
            # Get player's team
            player_team = None
            if player and player.current_team_id:
                from app.models.team import Team
                team = db.query(Team).filter(Team.team_id == player.current_team_id).first()
                player_team = team.abbreviation if team else None
            
            # Get game time from schedule
            game_time = None
            if game:
                from app.models import GameSchedule
                schedule = db.query(GameSchedule).filter(GameSchedule.game_id == game.game_id).first()
                game_time = schedule.game_time if schedule else None

            # Get last 3 games for this stat type
            historical_data = get_last_n_games_for_stat(
                db=db,
                player_id=pred.player_id,
                stat_type=pred.stat_type,
                sport=sport,
                n_games=3,
                exclude_game_id=pred.game_id,
                include_lineup_analysis=True,
                current_game_id=pred.game_id
            )
            last_3_games = historical_data['games']
            
            result.append({
                **pred.__dict__,
                "player_name": player.name if player else f"Player {pred.player_id}",
                "player_team": player_team,
                "game_time": game_time.isoformat() if game_time else None,
                "last_3_games": last_3_games
            })
        
        return result
    finally:
        db.close()


@router.get("/player/{player_id}/game/{game_id}")
async def get_player_prediction(
    player_id: int,
    game_id: int,
    stat_type: str = Query("points", description="Stat type"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get prediction for a specific player in a game."""
    db = SessionLocal()
    try:
        # Validate sport
        if sport not in ['NBA', 'NFL']:
            raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}. Must be 'NBA' or 'NFL'")
        
        prediction = db.query(Prediction).filter(
            Prediction.player_id == player_id,
            Prediction.game_id == game_id,
            Prediction.stat_type == stat_type,
            Prediction.sport == sport
        ).first()
        
        if not prediction:
            raise HTTPException(status_code=404, detail="Prediction not found")
        
        player = db.query(Player).filter(
            Player.player_id == player_id,
            Player.sport == sport
        ).first()

        # Get last 3 games for this stat type
        historical_data = get_last_n_games_for_stat(
            db=db,
            player_id=player_id,
            stat_type=stat_type,
            sport=sport,
            n_games=3,
            exclude_game_id=game_id,
            analyze_lineup_context=True,
            current_game_id=game_id
        )
        last_3_games = historical_data['games']
        
        return {
            **prediction.__dict__,
            "player_name": player.name if player else f"Player {player_id}",
            "last_3_games": last_3_games
        }
    finally:
        db.close()


@router.get("/safe-bets")
async def get_safe_bets(
    game_date: Optional[str] = Query(None, description="Filter by game date (YYYY-MM-DD)"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)"),
    limit: int = Query(50, description="Maximum number of results")
):
    """Get all safe bet predictions."""
    db = SessionLocal()
    try:
        # Validate sport
        if sport not in ['NBA', 'NFL']:
            raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}. Must be 'NBA' or 'NFL'")
        
        query = db.query(Prediction).filter(
            Prediction.bet_type == "safe",
            Prediction.sport == sport
        )
        
        if game_date:
            # Parse date string (YYYY-MM-DD) to date object
            try:
                from datetime import datetime
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
                games = db.query(Game).filter(
                    Game.game_date == parsed_date,
                    Game.sport == sport
                ).all()
                game_ids = [g.game_id for g in games]
                query = query.filter(Prediction.game_id.in_(game_ids))
            except ValueError:
                # Invalid date format, ignore filter
                pass
        
        predictions = query.limit(limit).all()
        
        # Filter out predictions for players who didn't play (for finished games)
        # AND filter out injured players (for upcoming games) - OPTIMIZED with batch queries
        from app.models.player_game_stat import PlayerGameStat
        from app.services.injury_context import InjuryContext

        # Get all unique game_ids and player_ids for batch queries
        game_ids = list(set([p.game_id for p in predictions]))
        player_ids = list(set([p.player_id for p in predictions]))

        # Batch load all games and player stats
        games = {g.game_id: g for g in db.query(Game).filter(Game.game_id.in_(game_ids)).all()}
        player_stats = {(s.player_id, s.game_id): s for s in db.query(PlayerGameStat).filter(
            PlayerGameStat.player_id.in_(player_ids),
            PlayerGameStat.game_id.in_(game_ids),
            PlayerGameStat.minutes_played > 0
        ).all()}

        # Batch load injury statuses for all players
        from app.models.injury import Injury
        injuries = db.query(Injury).filter(
            Injury.player_id.in_(player_ids),
            Injury.status.in_(['Out', 'Doubtful', 'Questionable', 'Probable']),
            Injury.actual_return_date.is_(None)
        ).all()

        # Create injury status map
        injury_statuses = {}
        for injury in injuries:
            injury_statuses[injury.player_id] = {
                "player_id": injury.player_id,
                "status": injury.status,
                "injury_type": injury.injury_type,
                "injury_date": injury.injury_date.isoformat() if injury.injury_date else None,
                "expected_return_date": injury.expected_return_date.isoformat() if injury.expected_return_date else None,
                "description": injury.description
            }

        filtered_predictions = []
        for pred in predictions:
            game = games.get(pred.game_id)
            if game and game.game_status == 'finished':
                # Check if player actually played in finished game
                stat_key = (pred.player_id, pred.game_id)
                if stat_key not in player_stats:
                    continue
            elif game and game.game_status in ['scheduled', 'in_progress']:
                # For upcoming games, check injury status
                injury_status = injury_statuses.get(pred.player_id)
                if injury_status and injury_status['status'] in ['Out', 'Doubtful', 'Questionable']:
                    continue  # Skip injured players
            filtered_predictions.append(pred)

        predictions = filtered_predictions
        
        # Enrich with player and game info (optimized with batch queries)
        from app.models.team import Team
        from app.models import GameSchedule
        
        # Get all unique player_ids and game_ids
        player_ids = list(set([p.player_id for p in predictions]))
        game_ids = list(set([p.game_id for p in predictions]))
        
        # Batch load all players, games, teams, and schedules
        players = {p.player_id: p for p in db.query(Player).filter(Player.player_id.in_(player_ids)).all()}
        games = {g.game_id: g for g in db.query(Game).filter(Game.game_id.in_(game_ids)).all()}
        team_ids = list(set([p.current_team_id for p in players.values() if p.current_team_id]))
        teams = {t.team_id: t for t in db.query(Team).filter(Team.team_id.in_(team_ids)).all()} if team_ids else {}
        schedules = {s.game_id: s for s in db.query(GameSchedule).filter(GameSchedule.game_id.in_(game_ids)).all()}
        
        # Build result efficiently
        result = []
        for pred in predictions:
            player = players.get(pred.player_id)
            game = games.get(pred.game_id)
            
            # Get player's team
            player_team = None
            if player and player.current_team_id:
                team = teams.get(player.current_team_id)
                player_team = team.abbreviation if team else None
            
            # Get game time from schedule
            game_time = None
            schedule = schedules.get(pred.game_id)
            if schedule:
                game_time = schedule.game_time

            # Get last 3 games for this stat type
            historical_data = get_last_n_games_for_stat(
                db=db,
                player_id=pred.player_id,
                stat_type=pred.stat_type,
                sport=sport,
                n_games=3,
                exclude_game_id=pred.game_id,
                include_lineup_analysis=True,
                current_game_id=pred.game_id
            )
            last_3_games = historical_data['games']
            
            result.append({
                **pred.__dict__,
                "player_name": player.name if player else f"Player {pred.player_id}",
                "player_team": player_team,
                "game_date": game.game_date if game else None,
                "game_time": game_time.isoformat() if game_time else None,
                "last_3_games": last_3_games
            })
        
        return result
    finally:
        db.close()


@router.get("/long-shots")
async def get_long_shots(
    game_date: Optional[str] = Query(None, description="Filter by game date (YYYY-MM-DD)"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)"),
    limit: int = Query(50, description="Maximum number of results")
):
    """Get all long shot predictions."""
    db = SessionLocal()
    try:
        # Validate sport
        if sport not in ['NBA', 'NFL']:
            raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}. Must be 'NBA' or 'NFL'")
        
        query = db.query(Prediction).filter(
            Prediction.bet_type == "long_shot",
            Prediction.sport == sport
        )
        
        if game_date:
            # Parse date string (YYYY-MM-DD) to date object
            try:
                from datetime import datetime
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
                games = db.query(Game).filter(
                    Game.game_date == parsed_date,
                    Game.sport == sport
                ).all()
                game_ids = [g.game_id for g in games]
                query = query.filter(Prediction.game_id.in_(game_ids))
            except ValueError:
                # Invalid date format, ignore filter
                pass
        
        predictions = query.limit(limit).all()
        
        # Filter out predictions for players who didn't play (for finished games)
        # AND filter out players who are injured/not playing (for upcoming games) - OPTIMIZED
        from app.models.player_game_stat import PlayerGameStat
        from app.services.injury_context import InjuryContext

        # Get all unique game_ids and player_ids for batch queries
        game_ids = list(set([p.game_id for p in predictions]))
        player_ids = list(set([p.player_id for p in predictions]))

        # Batch load all games and player stats
        games = {g.game_id: g for g in db.query(Game).filter(Game.game_id.in_(game_ids)).all()}
        player_stats = {(s.player_id, s.game_id): s for s in db.query(PlayerGameStat).filter(
            PlayerGameStat.player_id.in_(player_ids),
            PlayerGameStat.game_id.in_(game_ids),
            PlayerGameStat.minutes_played > 0
        ).all()}

        # Batch load injury statuses for all players
        from app.models.injury import Injury
        injuries = db.query(Injury).filter(
            Injury.player_id.in_(player_ids),
            Injury.status.in_(['Out', 'Doubtful', 'Questionable', 'Probable']),
            Injury.actual_return_date.is_(None)
        ).all()

        # Create injury status map
        injury_statuses = {}
        for injury in injuries:
            injury_statuses[injury.player_id] = {
                "player_id": injury.player_id,
                "status": injury.status,
                "injury_type": injury.injury_type,
                "injury_date": injury.injury_date.isoformat() if injury.injury_date else None,
                "expected_return_date": injury.expected_return_date.isoformat() if injury.expected_return_date else None,
                "description": injury.description
            }

        filtered_predictions = []
        for pred in predictions:
            game = games.get(pred.game_id)
            if not game:
                continue

            # For finished games, check if player actually played
            if game.game_status == 'finished':
                stat_key = (pred.player_id, pred.game_id)
                if stat_key not in player_stats:
                    continue  # Player didn't play, skip

            # For upcoming games, check if player is injured or not playing
            elif game.game_status in ['scheduled', 'in_progress']:
                # Check injury status
                injury_status = injury_statuses.get(pred.player_id)
                if injury_status and injury_status['status'] in ['Out', 'Doubtful']:
                    continue  # Player is out, skip prediction

                # Additional filter: Skip predictions with very low projected stats
                if pred.distribution_mean:
                    min_thresholds = {
                        'points': 8.0,
                        'rebounds': 4.0,
                        'assists': 3.0
                    }
                    threshold = min_thresholds.get(pred.stat_type, 5.0)
                    if pred.distribution_mean < threshold:
                        continue  # Too low, unlikely to have betting lines

            filtered_predictions.append(pred)

        predictions = filtered_predictions
        
        # Enrich with player and game info (optimized with batch queries)
        from app.models.team import Team
        from app.models import GameSchedule
        
        # Get all unique player_ids and game_ids
        player_ids = list(set([p.player_id for p in predictions]))
        game_ids = list(set([p.game_id for p in predictions]))
        
        # Batch load all players, games, teams, and schedules
        players = {p.player_id: p for p in db.query(Player).filter(Player.player_id.in_(player_ids)).all()}
        games = {g.game_id: g for g in db.query(Game).filter(Game.game_id.in_(game_ids)).all()}
        team_ids = list(set([p.current_team_id for p in players.values() if p.current_team_id]))
        teams = {t.team_id: t for t in db.query(Team).filter(Team.team_id.in_(team_ids)).all()} if team_ids else {}
        schedules = {s.game_id: s for s in db.query(GameSchedule).filter(GameSchedule.game_id.in_(game_ids)).all()}
        
        # Build result efficiently
        result = []
        for pred in predictions:
            player = players.get(pred.player_id)
            game = games.get(pred.game_id)
            
            # Get player's team
            player_team = None
            if player and player.current_team_id:
                team = teams.get(player.current_team_id)
                player_team = team.abbreviation if team else None
            
            # Get game time from schedule
            game_time = None
            schedule = schedules.get(pred.game_id)
            if schedule:
                game_time = schedule.game_time
            
            result.append({
                **pred.__dict__,
                "player_name": player.name if player else f"Player {pred.player_id}",
                "player_team": player_team,
                "game_date": game.game_date if game else None,
                "game_time": game_time.isoformat() if game_time else None
            })
        
        return result
    finally:
        db.close()


@router.post("/generate")
async def generate_predictions(request: GeneratePredictionsRequest):
    """Generate predictions with progress updates via Server-Sent Events."""
    
    async def generate_with_progress():
        db = SessionLocal()
        progress_queue = []
        
        def progress_callback(update):
            progress_queue.append(update)
        
        try:
            # Validate sport
            if request.sport not in ['NBA', 'NFL']:
                yield f"data: {json.dumps({'error': f'Invalid sport: {request.sport}. Must be NBA or NFL'})}\n\n"
                return
            
            # Collect lineups for upcoming games before generating predictions
            # This ensures we have accurate starter information
            from datetime import date, timedelta
            from app.scrapers.lineup_scraper import LineupScraper
            
            if not request.game_id:  # Only collect for upcoming games (not single game)
                try:
                    today = date.today()
                    days_to_check = request.days_ahead if hasattr(request, 'days_ahead') else 2
                    end_date = today + timedelta(days=days_to_check)
                    
                    # Collect lineups for today and tomorrow, filtered by sport
                    lineup_scraper = LineupScraper(db_session=db)
                    for check_date in [today, today + timedelta(days=1)]:
                        if check_date <= end_date:
                            try:
                                lineup_scraper.collect_lineups_for_date(check_date, sport=request.sport)
                                db.commit()
                            except Exception as e:
                                logger.warning(f"Could not collect lineups for {check_date}: {e}")
                                db.rollback()
                except Exception as e:
                    logger.warning(f"Could not collect lineups before prediction generation: {e}")
                    # Continue anyway - predictions can still be generated
            
            service = PredictionService(db, sport=request.sport)
            
            if request.game_id:
                # Run in thread to avoid blocking
                import concurrent.futures
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        service.generate_predictions_for_game,
                        request.game_id,
                        request.stat_types,
                        progress_callback
                    )
                    
                    # Yield progress updates
                    while not future.done():
                        while progress_queue:
                            update = progress_queue.pop(0)
                            yield f"data: {json.dumps(update)}\n\n"
                        await asyncio.sleep(0.1)
                    
                    # Get final result
                    results = future.result()
                    yield f"data: {json.dumps({'progress': 100, 'complete': True, 'results': results})}\n\n"
            else:
                # Limit to 1 day to avoid timeout
                days = min(request.days_ahead, 1)
                
                import concurrent.futures
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        service.generate_predictions_for_upcoming_games,
                        days,
                        request.stat_types,
                        progress_callback
                    )
                    
                    # Yield progress updates
                    while not future.done():
                        while progress_queue:
                            update = progress_queue.pop(0)
                            yield f"data: {json.dumps(update)}\n\n"
                        await asyncio.sleep(0.1)
                    
                    # Get final result
                    results = future.result()
                    yield f"data: {json.dumps({'progress': 100, 'complete': True, 'results': results})}\n\n"
        except Exception as e:
            import traceback
            error_detail = f"{str(e)}\n{traceback.format_exc()}"
            yield f"data: {json.dumps({'error': error_detail, 'complete': True})}\n\n"
        finally:
            db.close()
    
    return StreamingResponse(
        generate_with_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/upcoming")
async def get_upcoming_predictions(
    days_ahead: int = Query(1, description="Days ahead to look"),
    stat_type: Optional[str] = Query(None, description="Filter by stat type"),
    bet_type: Optional[str] = Query(None, description="Filter by bet type"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get predictions for upcoming games."""
    db = SessionLocal()
    try:
        # Validate sport
        if sport not in ['NBA', 'NFL']:
            raise HTTPException(status_code=400, detail=f"Invalid sport: {sport}. Must be 'NBA' or 'NFL'")
        
        from datetime import timedelta
        
        today = date.today()
        end_date = today + timedelta(days=days_ahead)
        
        games = db.query(Game).filter(
            Game.sport == sport,
            Game.game_date >= today,
            Game.game_date <= end_date,
            Game.game_status.in_(['scheduled', 'in_progress'])
        ).all()
        
        game_ids = [g.game_id for g in games]
        
        query = db.query(Prediction).filter(
            Prediction.game_id.in_(game_ids),
            Prediction.sport == sport
        )
        
        if stat_type:
            query = query.filter(Prediction.stat_type == stat_type)
        
        if bet_type:
            query = query.filter(Prediction.bet_type == bet_type)
        
        predictions = query.all()
        
        # Filter out injured players for upcoming games
        from app.services.injury_context import InjuryContext
        injury_context = InjuryContext(db)
        
        healthy_predictions = []
        for pred in predictions:
            game = db.query(Game).filter(Game.game_id == pred.game_id).first()
            if game and game.game_status in ['scheduled', 'in_progress']:
                # Check injury status
                injury_status = injury_context.get_player_injury_status(pred.player_id)
                if injury_status and injury_status['status'] in ['Out', 'Doubtful', 'Questionable']:
                    continue  # Skip injured players
            healthy_predictions.append(pred)
        predictions = healthy_predictions
        
        # Enrich with player and game info (filter by sport)
        result = []
        for pred in predictions:
            player = db.query(Player).filter(
                Player.player_id == pred.player_id,
                Player.sport == sport
            ).first()
            game = db.query(Game).filter(
                Game.game_id == pred.game_id,
                Game.sport == sport
            ).first()
            
            # Get player's team
            player_team = None
            if player and player.current_team_id:
                from app.models.team import Team
                team = db.query(Team).filter(
                    Team.team_id == player.current_team_id,
                    Team.sport == sport
                ).first()
                player_team = team.abbreviation if team else None
            
            # Get game time from schedule
            game_time = None
            if game:
                from app.models import GameSchedule
                schedule = db.query(GameSchedule).filter(
                    GameSchedule.game_id == game.game_id,
                    GameSchedule.sport == sport
                ).first()
                game_time = schedule.game_time if schedule else None

            # Get last 3 games for this stat type
            historical_data = get_last_n_games_for_stat(
                db=db,
                player_id=pred.player_id,
                stat_type=pred.stat_type,
                sport=sport,
                n_games=3,
                exclude_game_id=pred.game_id,
                include_lineup_analysis=True,
                current_game_id=pred.game_id
            )
            last_3_games = historical_data['games']
            
            result.append({
                **pred.__dict__,
                "player_name": player.name if player else f"Player {pred.player_id}",
                "player_team": player_team,
                "game_date": game.game_date if game else None,
                "game_time": game_time.isoformat() if game_time else None,
                "home_team_id": game.home_team_id if game else None,
                "away_team_id": game.away_team_id if game else None,
                "last_3_games": last_3_games
            })
        
        return result
    finally:
        db.close()

