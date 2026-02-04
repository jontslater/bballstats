"""
Suggested Bets API endpoints.
"""
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import date, datetime
from app.database import SessionLocal
from app.services.suggested_bets import SuggestedBetsService
from app.services.builder_plays import BuilderPlaysService

router = APIRouter(prefix="/api/suggested-bets", tags=["suggested-bets"])


@router.get("/bets")
async def get_suggested_bets(
    game_date: Optional[str] = Query(None, description="Filter by game date (YYYY-MM-DD)"),
    limit: int = Query(10, description="Maximum number of suggestions"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get suggested bets for a specific date."""
    db = SessionLocal()
    try:
        service = SuggestedBetsService(db, sport)

        parsed_date = None
        if game_date:
            try:
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
                print(f"Filtering suggested bets by date: {parsed_date}")
            except ValueError:
                print(f"Invalid date format: {game_date}")
                pass
        else:
            print("No date filter provided - will use today's date")

        suggestions = service.get_suggested_bets(game_date=parsed_date, limit=limit)
        print(f"API returning {len(suggestions)} suggested bets")
        return suggestions
    finally:
        db.close()


@router.get("/parlays")
async def get_suggested_parlays(
    game_date: Optional[str] = Query(None, description="Filter by game date (YYYY-MM-DD)"),
    limit: int = Query(5, description="Maximum number of parlay suggestions"),
    mix_stats: bool = Query(True, description="Prefer parlays with mix of stat types"),
    diversify_players: bool = Query(True, description="Ensure each player appears in only one parlay"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get suggested parlay combinations with player diversification."""
    db = SessionLocal()
    try:
        service = SuggestedBetsService(db, sport)
        
        parsed_date = None
        if game_date:
            try:
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        if mix_stats:
            suggestions = service.get_suggested_parlays_by_stat_mix(
                game_date=parsed_date, 
                limit=limit,
                diversify_players=diversify_players
            )
        else:
            suggestions = service.get_suggested_parlays(
                game_date=parsed_date, 
                limit=limit,
                diversify_players=diversify_players
            )
        
        return suggestions
    finally:
        db.close()


@router.get("/matchup-advantage-bets")
async def get_matchup_advantage_bets(
    game_date: Optional[str] = Query(None, description="Game date (YYYY-MM-DD format). Defaults to today."),
    limit: int = Query(10, description="Maximum number of bet suggestions to return", ge=1, le=50),
    only_hot: bool = Query(True, description="If true, only include players with strong matchup advantages. If false, include both hot and cold."),
    sport: str = Query("NBA", description="Sport type (NBA or NFL)")
):
    """
    Get individual suggested bets specifically for players with matchup advantages.

    Returns individual bets for players who have strong (or weak) historical performance
    against their current opponents.
    """
    try:
        parsed_date = None
        if game_date:
            try:
                parsed_date = datetime.fromisoformat(game_date).date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

        db = SessionLocal()
        service = SuggestedBetsService(db, sport)

        suggestions = service.get_matchup_advantage_bets(
            game_date=parsed_date,
            limit=limit,
            only_hot=only_hot
        )

        return suggestions
    finally:
        db.close()


@router.post("/backfill-lines")
async def backfill_prediction_lines():
    """Backfill missing line values for existing predictions."""
    from app.services.prediction_service import PredictionService

    db = SessionLocal()
    try:
        # Simple backfill logic
        predictions = db.query(Prediction).filter(
            Prediction.safe_line.is_(None) |
            Prediction.standard_line.is_(None) |
            Prediction.long_shot_line.is_(None)
        ).limit(100).all()

        updated_count = 0
        for pred in predictions:
            # Calculate lines based on distribution mean
            if pred.distribution_mean:
                if pred.bet_type == 'safe' and pred.safe_line is None:
                    pred.safe_line = round(pred.distribution_mean * 1.2, 1)
                elif pred.bet_type == 'standard' and pred.standard_line is None:
                    pred.standard_line = round(pred.distribution_mean, 1)
                elif pred.bet_type == 'long_shot' and pred.long_shot_line is None:
                    pred.long_shot_line = round(pred.distribution_mean * 0.8, 1)

                # Set default probabilities if missing
                if pred.bet_type == 'safe' and pred.safe_probability is None:
                    pred.safe_probability = 0.75
                elif pred.bet_type == 'standard' and pred.standard_probability is None:
                    pred.standard_probability = 0.60
                elif pred.bet_type == 'long_shot' and pred.long_shot_probability is None:
                    pred.long_shot_probability = 0.25

                updated_count += 1

        db.commit()

        return {
            "success": True,
            "message": f"Backfilled lines for {updated_count} predictions",
            "updated_count": updated_count
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/matchup-advantage-parlays")
async def get_matchup_advantage_parlays(
    game_date: Optional[str] = Query(None, description="Game date (YYYY-MM-DD format). Defaults to today."),
    limit: int = Query(3, description="Maximum number of parlay suggestions to return", ge=1, le=10),
    min_legs: int = Query(2, description="Minimum number of legs in each parlay", ge=2, le=4),
    max_legs: int = Query(4, description="Maximum number of legs in each parlay", ge=2, le=4),
    sport: str = Query("NBA", description="Sport type (NBA or NFL)")
):
    """
    Get suggested parlays specifically for players with HOT matchup advantages.

    Returns parlays of 2-4 players who have strong historical performance
    against their current opponents (excludes players with weak/cold matchups).
    """
    try:
        parsed_date = None
        if game_date:
            try:
                parsed_date = datetime.fromisoformat(game_date).date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

        db = SessionLocal()
        service = SuggestedBetsService(db, sport)

        suggestions = service.get_matchup_advantage_parlays(
            game_date=parsed_date,
            limit=limit,
            min_legs=min_legs,
            max_legs=max_legs
        )

        return suggestions
    finally:
        db.close()


@router.get("/safe-long-parlays")
async def get_safe_long_parlays(
    game_date: Optional[str] = Query(None, description="Filter by game date (YYYY-MM-DD)"),
    limit: int = Query(3, description="Maximum number of parlay suggestions"),
    num_legs: int = Query(12, description="Number of legs in parlay (10-15)"),
    min_leg_probability: float = Query(0.75, description="Minimum probability for each leg (0.75 = 75%)"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get long parlays (10-15 legs) made of very safe bets."""
    db = SessionLocal()
    try:
        service = SuggestedBetsService(db, sport)
        
        parsed_date = None
        if game_date:
            try:
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        suggestions = service.get_safe_long_parlays(
            game_date=parsed_date,
            limit=limit,
            num_legs=num_legs,
            min_leg_probability=min_leg_probability
        )
        
        return suggestions
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error getting safe long parlays for {sport}: {e}")
        print(error_details)
        raise HTTPException(status_code=500, detail=f"Failed to get safe long parlays: {str(e)}")
    finally:
        db.close()


@router.get("/same-game-parlays/{game_id}")
async def get_same_game_parlays(
    game_id: int,
    limit: int = Query(5, description="Maximum number of parlay suggestions"),
    num_legs: int = Query(3, description="Number of legs in parlay (2-4)"),
    min_leg_probability: float = Query(0.70, description="Minimum probability for each leg (0.70 = 70%)"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get same-game parlay suggestions (all legs from the same game)."""
    db = SessionLocal()
    try:
        service = SuggestedBetsService(db, sport)
        
        suggestions = service.get_same_game_parlays(
            game_id=game_id,
            limit=limit,
            num_legs=num_legs,
            min_leg_probability=min_leg_probability
        )
        
        return suggestions
    finally:
        db.close()


@router.get("/builder-plays")
async def get_builder_plays(
    game_date: Optional[str] = Query(None, description="Filter by game date (YYYY-MM-DD)"),
    limit: int = Query(5, description="Maximum number of builder plays"),
    num_legs: int = Query(2, description="Number of legs (2 or 3)"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get builder plays - safe parlays designed to double money."""
    db = SessionLocal()
    try:
        service = BuilderPlaysService(db, sport)
        
        parsed_date = None
        if game_date:
            try:
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        if num_legs not in [2, 3]:
            num_legs = 2
        
        builder_plays = service.get_builder_plays(
            game_date=parsed_date,
            limit=limit,
            num_legs=num_legs
        )
        
        return builder_plays
    finally:
        db.close()


class RefreshSafeLongParlayRequest(BaseModel):
    """Request to refresh a safe long parlay."""
    game_date: Optional[str] = None
    num_legs: int = 12
    min_leg_probability: float = 0.75
    exclude_player_ids: List[int] = []


class RefreshBuilderPlayRequest(BaseModel):
    """Request to refresh a builder play."""
    game_date: Optional[str] = None
    num_legs: int = 2
    exclude_player_ids: List[int] = []


@router.post("/refresh-safe-long-parlay")
async def refresh_safe_long_parlay(request: RefreshSafeLongParlayRequest):
    """Generate a new safe long parlay, excluding specified player IDs."""
    refresh_req = request
    
    db = SessionLocal()
    try:
        service = SuggestedBetsService(db)
        
        parsed_date = None
        if refresh_req.game_date:
            try:
                parsed_date = datetime.strptime(refresh_req.game_date, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # Generate a new parlay excluding the specified players
        # Try with exclusions first
        new_parlay = service.get_safe_long_parlays(
            game_date=parsed_date,
            limit=1,
            num_legs=refresh_req.num_legs,
            min_leg_probability=refresh_req.min_leg_probability,
            exclude_player_ids=refresh_req.exclude_player_ids
        )
        
        # If we can't generate one with exclusions, try without (to ensure we always return something)
        if not new_parlay and refresh_req.exclude_player_ids:
            new_parlay = service.get_safe_long_parlays(
                game_date=parsed_date,
                limit=1,
                num_legs=refresh_req.num_legs,
                min_leg_probability=refresh_req.min_leg_probability,
                exclude_player_ids=[]  # Try without exclusions
            )
        
        if new_parlay:
            return new_parlay[0]
        else:
            raise HTTPException(
                status_code=404, 
                detail=f"Could not generate a new {refresh_req.num_legs}-leg parlay. Not enough players with {refresh_req.min_leg_probability*100}%+ probability available. Try generating more predictions or lowering the probability threshold."
            )
    finally:
        db.close()


@router.post("/refresh-builder-play")
async def refresh_builder_play(request: RefreshBuilderPlayRequest):
    """Generate a new builder play, excluding specified player IDs."""
    refresh_req = request
    
    db = SessionLocal()
    try:
        service = BuilderPlaysService(db)
        
        parsed_date = None
        if refresh_req.game_date:
            try:
                parsed_date = datetime.strptime(refresh_req.game_date, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        if refresh_req.num_legs not in [2, 3]:
            refresh_req.num_legs = 2
        
        # Generate a new builder play excluding the specified players
        new_play = service.get_builder_plays(
            game_date=parsed_date,
            limit=1,
            num_legs=refresh_req.num_legs,
            exclude_player_ids=refresh_req.exclude_player_ids
        )
        
        if new_play:
            return new_play[0]
        else:
            raise HTTPException(status_code=404, detail="Could not generate a new builder play. Try again or check if enough predictions are available.")
    finally:
        db.close()


