"""
User Play API endpoints.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from pydantic import BaseModel
from app.database import SessionLocal
from app.models.user_play import UserPlay
from app.models.player import Player
from app.models.game import Game

router = APIRouter(prefix="/api/plays", tags=["plays"])


class CreatePlayRequest(BaseModel):
    """Request to create a play."""
    player_id: int
    game_id: int
    stat_type: str  # points, rebounds, assists, minutes
    bet_line: str  # e.g., "Over 24.5"
    notes: Optional[str] = None


class UpdatePlayRequest(BaseModel):
    """Request to update a play."""
    status: Optional[str] = None  # pending, hit, miss
    actual_result: Optional[int] = None
    notes: Optional[str] = None


@router.get("")
async def get_plays(
    status: Optional[str] = None,
    limit: int = 100
):
    """Get all plays that are NOT part of any parlay."""
    db = SessionLocal()
    try:
        from app.models.parlay import parlay_plays, Parlay
        from sqlalchemy import select, exists
        
        # Use a subquery to check if a play exists in any parlay
        # This is more reliable than manually querying the association table
        parlay_play_subquery = select(parlay_plays.c.play_id).distinct()
        
        query = db.query(UserPlay).filter(
            ~UserPlay.play_id.in_(parlay_play_subquery)
        )
        
        if status:
            query = query.filter(UserPlay.status == status)
        
        plays = query.order_by(UserPlay.created_at.desc()).limit(limit).all()
        
        # Enrich with player and game info
        result = []
        for play in plays:
            player = db.query(Player).filter(Player.player_id == play.player_id).first()
            game = db.query(Game).filter(Game.game_id == play.game_id).first()
            
            result.append({
                **play.__dict__,
                "player_name": player.name if player else None,
                "game_date": game.game_date.isoformat() if game else None
            })
        
        return result
    finally:
        db.close()


@router.post("")
async def create_play(request: CreatePlayRequest):
    """Create a new play."""
    db = SessionLocal()
    try:
        # Verify player and game exist (skip player check for team bets with player_id=0)
        if request.player_id > 0:
            player = db.query(Player).filter(Player.player_id == request.player_id).first()
            if not player:
                raise HTTPException(status_code=404, detail="Player not found")
        
        game = db.query(Game).filter(Game.game_id == request.game_id).first()
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        # Get prediction for this player/game/stat (if it exists)
        # Advanced bets might not have a corresponding prediction
        from app.models.prediction import Prediction
        prediction = None
        if request.stat_type != 'combo' and request.player_id > 0:
            prediction = db.query(Prediction).filter(
                Prediction.player_id == request.player_id,
                Prediction.game_id == request.game_id,
                Prediction.stat_type == request.stat_type
            ).first()
        
        play = UserPlay(
            player_id=request.player_id,
            game_id=request.game_id,
            stat_type=request.stat_type,
            bet_line=request.bet_line,
            notes=request.notes,
            predicted_min=int(prediction.percentile_25) if prediction else None,
            predicted_max=int(prediction.percentile_85) if prediction else None,
            likelihood_score=prediction.safe_probability if prediction else None,
            status="pending"
        )
        
        db.add(play)
        db.commit()
        db.refresh(play)
        
        return {
            "play_id": play.play_id,
            "message": "Play created successfully"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/{play_id}")
async def get_play(play_id: int):
    """Get play details."""
    db = SessionLocal()
    try:
        play = db.query(UserPlay).filter(UserPlay.play_id == play_id).first()
        
        if not play:
            raise HTTPException(status_code=404, detail="Play not found")
        
        player = db.query(Player).filter(Player.player_id == play.player_id).first()
        game = db.query(Game).filter(Game.game_id == play.game_id).first()
        
        return {
            **play.__dict__,
            "player_name": player.name if player else None,
            "game_date": game.game_date.isoformat() if game else None
        }
    finally:
        db.close()


@router.put("/{play_id}")
async def update_play(play_id: int, request: UpdatePlayRequest):
    """Update a play."""
    db = SessionLocal()
    try:
        play = db.query(UserPlay).filter(UserPlay.play_id == play_id).first()
        
        if not play:
            raise HTTPException(status_code=404, detail="Play not found")
        
        if request.status:
            play.status = request.status
        
        if request.actual_result is not None:
            play.actual_result = request.actual_result
        
        if request.notes is not None:
            play.notes = request.notes
        
        db.commit()
        db.refresh(play)
        
        return {
            "play_id": play.play_id,
            "message": "Play updated successfully"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.delete("/{play_id}")
async def delete_play(play_id: int):
    """Delete a play."""
    db = SessionLocal()
    try:
        play = db.query(UserPlay).filter(UserPlay.play_id == play_id).first()
        
        if not play:
            raise HTTPException(status_code=404, detail="Play not found")
        
        db.delete(play)
        db.commit()
        
        return {"message": "Play deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/stats/summary")
async def get_play_stats():
    """Get play performance statistics.
    
    Counts:
    - Standalone plays (not in parlays) as individual plays
    - Parlays as 1 play each
    """
    db = SessionLocal()
    try:
        from app.models.parlay import parlay_plays, Parlay
        from sqlalchemy import select
        
        # Use subquery to get plays that are NOT in any parlay
        parlay_play_subquery = select(parlay_plays.c.play_id).distinct()
        
        # Count standalone plays (not in parlays)
        standalone_query = db.query(UserPlay).filter(
            ~UserPlay.play_id.in_(parlay_play_subquery)
        )
        
        total_standalone = standalone_query.count()
        hit_standalone = standalone_query.filter(UserPlay.status == "hit").count()
        miss_standalone = standalone_query.filter(UserPlay.status == "miss").count()
        pending_standalone = standalone_query.filter(UserPlay.status == "pending").count()
        
        # Count parlays (each parlay counts as 1 play)
        total_parlays = db.query(Parlay).count()
        hit_parlays = db.query(Parlay).filter(Parlay.status == "hit").count()
        miss_parlays = db.query(Parlay).filter(Parlay.status == "miss").count()
        pending_parlays = db.query(Parlay).filter(Parlay.status == "pending").count()
        
        # Combined totals
        total_plays = total_standalone + total_parlays
        hit_plays = hit_standalone + hit_parlays
        miss_plays = miss_standalone + miss_parlays
        pending_plays = pending_standalone + pending_parlays
        
        hit_rate = (hit_plays / (hit_plays + miss_plays) * 100) if (hit_plays + miss_plays) > 0 else 0
        
        return {
            "total_plays": total_plays,
            "hit": hit_plays,
            "miss": miss_plays,
            "pending": pending_plays,
            "hit_rate": round(hit_rate, 2),
            "standalone_plays": total_standalone,
            "parlays": total_parlays
        }
    finally:
        db.close()

