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
    limit: int = Query(10, description="Maximum number of suggestions")
):
    """Get suggested bets for a specific date."""
    db = SessionLocal()
    try:
        service = SuggestedBetsService(db)
        
        parsed_date = None
        if game_date:
            try:
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        suggestions = service.get_suggested_bets(game_date=parsed_date, limit=limit)
        return suggestions
    finally:
        db.close()


@router.get("/parlays")
async def get_suggested_parlays(
    game_date: Optional[str] = Query(None, description="Filter by game date (YYYY-MM-DD)"),
    limit: int = Query(5, description="Maximum number of parlay suggestions"),
    mix_stats: bool = Query(True, description="Prefer parlays with mix of stat types"),
    diversify_players: bool = Query(True, description="Ensure each player appears in only one parlay")
):
    """Get suggested parlay combinations with player diversification."""
    db = SessionLocal()
    try:
        service = SuggestedBetsService(db)
        
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


@router.get("/safe-long-parlays")
async def get_safe_long_parlays(
    game_date: Optional[str] = Query(None, description="Filter by game date (YYYY-MM-DD)"),
    limit: int = Query(3, description="Maximum number of parlay suggestions"),
    num_legs: int = Query(12, description="Number of legs in parlay (10-15)"),
    min_leg_probability: float = Query(0.75, description="Minimum probability for each leg (0.75 = 75%)")
):
    """Get long parlays (10-15 legs) made of very safe bets."""
    db = SessionLocal()
    try:
        service = SuggestedBetsService(db)
        
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
    finally:
        db.close()


@router.get("/same-game-parlays/{game_id}")
async def get_same_game_parlays(
    game_id: int,
    limit: int = Query(5, description="Maximum number of parlay suggestions"),
    num_legs: int = Query(3, description="Number of legs in parlay (2-4)"),
    min_leg_probability: float = Query(0.70, description="Minimum probability for each leg (0.70 = 70%)")
):
    """Get same-game parlay suggestions (all legs from the same game)."""
    db = SessionLocal()
    try:
        service = SuggestedBetsService(db)
        
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
    num_legs: int = Query(2, description="Number of legs (2 or 3)")
):
    """Get builder plays - safe parlays designed to double money."""
    db = SessionLocal()
    try:
        service = BuilderPlaysService(db)
        
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

