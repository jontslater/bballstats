"""
Parlay API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, insert, and_
from typing import List, Optional
from pydantic import BaseModel
from datetime import date
from app.database import SessionLocal
from app.models.parlay import Parlay, parlay_plays
from app.models.user_play import UserPlay
from app.models.player import Player
from app.models.game import Game
from app.services.text_parlay_parser import TextParlayParser

router = APIRouter(prefix="/api/parlays", tags=["parlays"])


class CreateParlayRequest(BaseModel):
    """Request to create a parlay."""
    play_ids: List[int]  # List of play IDs to include
    name: Optional[str] = None
    notes: Optional[str] = None


class UpdateParlayRequest(BaseModel):
    """Request to update a parlay."""
    name: Optional[str] = None
    notes: Optional[str] = None
    play_ids: Optional[List[int]] = None  # Update plays in parlay


class TextParlayRequest(BaseModel):
    """Request to create parlay from text."""
    text: str
    game_date: Optional[str] = None  # ISO format date string
    name: Optional[str] = None
    notes: Optional[str] = None


@router.post("")
async def create_parlay(request: CreateParlayRequest):
    """Create a new parlay."""
    db = SessionLocal()
    try:
        if len(request.play_ids) < 2:
            raise HTTPException(status_code=400, detail="Parlay must have at least 2 plays")
        
        # Verify all plays exist
        plays = db.query(UserPlay).filter(UserPlay.play_id.in_(request.play_ids)).all()
        if len(plays) != len(request.play_ids):
            raise HTTPException(status_code=400, detail="One or more plays not found")
        
        # Calculate combined probability and odds
        # Assuming each play has a probability (from prediction)
        total_probability = 1.0
        for play in plays:
            # Get probability from prediction if available
            # For now, use a default if not available
            prob = play.likelihood_score if play.likelihood_score else 0.5
            total_probability *= prob
        
        # Convert probability to odds (American format)
        # Use same formula as builder_plays for consistency
        if total_probability > 0:
            decimal_odds = 1.0 / total_probability
            if decimal_odds < 2.0:  # Probability > 50%
                total_odds = -100 / (decimal_odds - 1)
            else:  # Probability <= 50%
                total_odds = 100 * (decimal_odds - 1)
        else:
            total_odds = None
        
        # Create parlay
        parlay = Parlay(
            name=request.name,
            total_odds=total_odds,
            total_probability=total_probability,
            total_legs=len(plays),
            legs_hit=0,
            status="pending",
            notes=request.notes
        )
        db.add(parlay)
        db.flush()  # Get parlay_id
        
        # Associate plays with parlay using relationship
        # SQLAlchemy will handle the association table automatically
        parlay.plays = plays
        
        # Explicitly flush to ensure associations are written to parlay_plays table
        db.flush()
        
        # Verify associations were created
        from app.models.parlay import parlay_plays
        from sqlalchemy import select
        associations = db.execute(
            select(parlay_plays).where(parlay_plays.c.parlay_id == parlay.parlay_id)
        ).fetchall()
        
        if len(associations) != len(plays):
            # If associations weren't created via relationship, create them manually
            for play in plays:
                db.execute(
                    parlay_plays.insert().values(
                        parlay_id=parlay.parlay_id,
                        play_id=play.play_id
                    )
                )
            db.flush()
        
        db.commit()
        db.refresh(parlay)
        
        return {
            "parlay_id": parlay.parlay_id,
            "name": parlay.name,
            "total_odds": parlay.total_odds,
            "total_probability": parlay.total_probability,
            "total_legs": parlay.total_legs,
            "status": parlay.status,
            "plays": [
                {
                    "play_id": p.play_id,
                    "player_id": p.player_id,
                    "game_id": p.game_id,
                    "stat_type": p.stat_type,
                    "bet_line": p.bet_line
                }
                for p in plays
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("")
async def get_parlays(status: Optional[str] = None):
    """Get all parlays."""
    db = SessionLocal()
    try:
        query = db.query(Parlay)
        
        if status:
            query = query.filter(Parlay.status == status)
        
        parlays = query.order_by(Parlay.created_at.desc()).all()
        
        result = []
        for parlay in parlays:
            # Enrich with play details
            plays_data = []
            for play in parlay.plays:
                player = db.query(Player).filter(Player.player_id == play.player_id).first()
                game = db.query(Game).filter(Game.game_id == play.game_id).first()
                
                plays_data.append({
                    "play_id": play.play_id,
                    "player_id": play.player_id,
                    "player_name": player.name if player else f"Player {play.player_id}",
                    "game_id": play.game_id,
                    "game_date": game.game_date.isoformat() if game else None,
                    "stat_type": play.stat_type,
                    "bet_line": play.bet_line,
                    "status": play.status,
                    "actual_result": play.actual_result
                })
            
            result.append({
                "parlay_id": parlay.parlay_id,
                "name": parlay.name,
                "total_odds": parlay.total_odds,
                "total_probability": parlay.total_probability,
                "total_legs": parlay.total_legs,
                "legs_hit": parlay.legs_hit,
                "status": parlay.status,
                "notes": parlay.notes,
                "created_at": parlay.created_at.isoformat() if parlay.created_at else None,
                "plays": plays_data
            })
        
        return result
    finally:
        db.close()


@router.get("/{parlay_id}")
async def get_parlay(parlay_id: int):
    """Get a specific parlay."""
    db = SessionLocal()
    try:
        parlay = db.query(Parlay).filter(Parlay.parlay_id == parlay_id).first()
        
        if not parlay:
            raise HTTPException(status_code=404, detail="Parlay not found")
        
        # Enrich with play details
        plays_data = []
        for play in parlay.plays:
            player = db.query(Player).filter(Player.player_id == play.player_id).first()
            game = db.query(Game).filter(Game.game_id == play.game_id).first()
            
            plays_data.append({
                "play_id": play.play_id,
                "player_id": play.player_id,
                "player_name": player.name if player else f"Player {play.player_id}",
                "game_id": play.game_id,
                "game_date": game.game_date.isoformat() if game else None,
                "stat_type": play.stat_type,
                "bet_line": play.bet_line,
                "status": play.status,
                "actual_result": play.actual_result
            })
        
        return {
            "parlay_id": parlay.parlay_id,
            "name": parlay.name,
            "total_odds": parlay.total_odds,
            "total_probability": parlay.total_probability,
            "total_legs": parlay.total_legs,
            "legs_hit": parlay.legs_hit,
            "status": parlay.status,
            "notes": parlay.notes,
            "created_at": parlay.created_at.isoformat() if parlay.created_at else None,
            "plays": plays_data
        }
    finally:
        db.close()


@router.put("/{parlay_id}")
async def update_parlay(parlay_id: int, request: UpdateParlayRequest):
    """Update a parlay."""
    db = SessionLocal()
    try:
        parlay = db.query(Parlay).filter(Parlay.parlay_id == parlay_id).first()
        
        if not parlay:
            raise HTTPException(status_code=404, detail="Parlay not found")
        
        if request.name is not None:
            parlay.name = request.name
        if request.notes is not None:
            parlay.notes = request.notes
        
        if request.play_ids is not None:
            # Update plays in parlay
            plays = db.query(UserPlay).filter(UserPlay.play_id.in_(request.play_ids)).all()
            if len(plays) != len(request.play_ids):
                raise HTTPException(status_code=400, detail="One or more plays not found")
            
            parlay.plays = plays
            parlay.total_legs = len(plays)
            
            # Recalculate odds
            total_probability = 1.0
            for play in plays:
                prob = play.likelihood_score if play.likelihood_score else 0.5
                total_probability *= prob
            
            if total_probability > 0:
                decimal_odds = 1.0 / total_probability
                parlay.total_odds = (decimal_odds - 1) * 100
            else:
                parlay.total_odds = None
            
            parlay.total_probability = total_probability
        
        db.commit()
        db.refresh(parlay)
        
        return {"success": True, "parlay_id": parlay.parlay_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.delete("/{parlay_id}")
async def delete_parlay(parlay_id: int):
    """Delete a parlay."""
    db = SessionLocal()
    try:
        parlay = db.query(Parlay).filter(Parlay.parlay_id == parlay_id).first()
        
        if not parlay:
            raise HTTPException(status_code=404, detail="Parlay not found")
        
        db.delete(parlay)
        db.commit()
        
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/parse-text")
async def parse_text_to_bets(request: TextParlayRequest):
    """Parse text and match to predictions without creating a parlay."""
    db = SessionLocal()
    try:
        parser = TextParlayParser(db)
        
        game_date = None
        if request.game_date:
            from datetime import datetime
            game_date = datetime.fromisoformat(request.game_date.replace('Z', '+00:00')).date()
        
        parsed_bets = parser.parse_text(request.text)
        matched_bets = parser.match_to_predictions(parsed_bets, game_date)
        
        # Include debug info about unmatched bets
        unmatched_info = []
        for bet in parsed_bets:
            if not any(m['player_name'].lower() == bet['player_name'].lower() and 
                      m['stat_type'] == bet['stat_type'] for m in matched_bets):
                # Try to find the player to see if they exist
                from sqlalchemy import or_
                name_parts = bet['player_name'].strip().split()
                last_name = name_parts[-1] if name_parts else bet['player_name']
                
                player = db.query(Player).filter(
                    Player.name.ilike(f'%{last_name}%')
                ).first()
                
                if player:
                    # Player exists, check if they have predictions
                    from app.models.prediction import Prediction
                    pred_query = db.query(Prediction).filter(
                        and_(
                            Prediction.player_id == player.player_id,
                            Prediction.stat_type == bet['stat_type'],
                            Prediction.bet_type.in_(['safe', 'standard', 'long_shot'])
                        )
                    )
                    if game_date:
                        pred_query = pred_query.join(Game).filter(Game.game_date == game_date)
                    
                    pred_count = pred_query.count()
                    unmatched_info.append({
                        'player_name': bet['player_name'],
                        'stat_type': bet['stat_type'],
                        'matched_player': player.name if player else None,
                        'has_predictions': pred_count > 0,
                        'prediction_count': pred_count
                    })
                else:
                    unmatched_info.append({
                        'player_name': bet['player_name'],
                        'stat_type': bet['stat_type'],
                        'matched_player': None,
                        'has_predictions': False,
                        'prediction_count': 0
                    })
        
        return {
            "parsed_count": len(parsed_bets),
            "matched_count": len(matched_bets),
            "matched_bets": [
                {
                    "player_id": bet.get("player_id"),
                    "player_name": bet.get("player_name"),
                    "game_id": bet.get("game_id"),
                    "game_date": bet.get("game_date"),
                    "stat_type": bet.get("stat_type"),
                    "bet_type": bet.get("bet_type"),
                    "bet_line": bet.get("bet_line"),
                    "line": bet.get("line"),
                    "matched_line": bet.get("matched_line"),
                    "prediction_id": bet.get("prediction_id", -1),  # Default to -1 if None
                    "confidence": bet.get("confidence", 0.5)
                }
                for bet in matched_bets
                if bet is not None  # Filter out None results
            ],
            "unmatched_bets": [
                {
                    "player_name": bet["player_name"],
                    "stat_type": bet["stat_type"],
                    "bet_type": bet["bet_type"],
                    "line": bet["line"]
                }
                for bet in parsed_bets
                if not any(m["player_name"].lower() == bet["player_name"].lower() and m["stat_type"] == bet["stat_type"] for m in matched_bets)
            ],
            "unmatched_info": unmatched_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/from-text")
async def create_parlay_from_text(request: TextParlayRequest):
    """Create a parlay from text input."""
    db = SessionLocal()
    try:
        # Parse the text
        parser = TextParlayParser(db)
        
        # Parse game date if provided
        game_date = None
        if request.game_date:
            from datetime import datetime
            game_date = datetime.fromisoformat(request.game_date.replace('Z', '+00:00')).date()
        
        # Parse text into bets
        parsed_bets = parser.parse_text(request.text)
        
        if len(parsed_bets) < 2:
            raise HTTPException(
                status_code=400, 
                detail=f"Could not parse at least 2 bets from text. Found {len(parsed_bets)} bets. Format: 'Player Name Over X.X points, Player Name Over X.X rebounds'"
            )
        
        # Match to predictions
        matched_bets = parser.match_to_predictions(parsed_bets, game_date)
        
        if len(matched_bets) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"Could not match at least 2 bets to predictions. Matched {len(matched_bets)} out of {len(parsed_bets)}. Make sure players have predictions for today's games."
            )
        
        # Create plays for each matched bet
        from app.models.prediction import Prediction
        created_plays = []
        
        for match in matched_bets:
            pred = match.get('prediction')
            
            # Create or find existing play
            play = db.query(UserPlay).filter(
                and_(
                    UserPlay.player_id == match['player_id'],
                    UserPlay.game_id == match['game_id'],
                    UserPlay.stat_type == match['stat_type'],
                    UserPlay.bet_line == match['bet_line']
                )
            ).first()
            
            if not play:
                # Get probability from prediction if available, otherwise use estimated
                prob = None
                if pred:
                    if match['bet_type'] == 'Over':
                        if pred.safe_line and abs(pred.safe_line - match['line']) < 1.0:
                            prob = pred.safe_probability
                        elif pred.standard_line and abs(pred.standard_line - match['line']) < 1.0:
                            prob = pred.standard_probability
                        elif pred.long_shot_line and abs(pred.long_shot_line - match['line']) < 1.0:
                            prob = pred.long_shot_probability
                    prob = prob or pred.safe_probability or 0.5
                else:
                    # No prediction exists - use estimated probability from historical stats
                    prob = match.get('confidence', 0.5)
                
                # Get predicted min/max from prediction or estimate from historical stats
                predicted_min = None
                predicted_max = None
                if pred:
                    predicted_min = int(pred.percentile_25) if pred.percentile_25 else None
                    predicted_max = int(pred.percentile_85) if pred.percentile_85 else None
                else:
                    # Estimate from historical stats
                    estimated_mean = match.get('estimated_mean', match['line'])
                    estimated_std = match.get('estimated_std', estimated_mean * 0.2)
                    predicted_min = max(0, int(estimated_mean - estimated_std))
                    predicted_max = int(estimated_mean + estimated_std)
                
                # Ensure game_id is valid (not 0)
                game_id = match['game_id'] if match['game_id'] > 0 else None
                if not game_id:
                    # Try to find a game for today or upcoming
                    from datetime import date
                    today = date.today()
                    game = db.query(Game).filter(
                        Game.game_date >= today
                    ).order_by(Game.game_date.asc()).first()
                    if game:
                        game_id = game.game_id
                
                if not game_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Could not find a game for {match['player_name']}. Please ensure games are scheduled."
                    )
                
                play = UserPlay(
                    player_id=match['player_id'],
                    game_id=game_id,
                    stat_type=match['stat_type'],
                    bet_line=match['bet_line'],
                    notes=f"Created from text parlay: {request.text[:50]}",
                    predicted_min=predicted_min,
                    predicted_max=predicted_max,
                    likelihood_score=prob,
                    status="pending"
                )
                db.add(play)
                db.flush()
            
            created_plays.append(play)
        
        # Create parlay
        total_probability = 1.0
        for play in created_plays:
            prob = play.likelihood_score if play.likelihood_score else 0.5
            total_probability *= prob
        
        if total_probability > 0:
            decimal_odds = 1.0 / total_probability
            if decimal_odds < 2.0:
                total_odds = -100 / (decimal_odds - 1)
            else:
                total_odds = 100 * (decimal_odds - 1)
        else:
            total_odds = None
        
        parlay = Parlay(
            name=request.name or f"Text Parlay: {request.text[:30]}",
            total_odds=total_odds,
            total_probability=total_probability,
            total_legs=len(created_plays),
            legs_hit=0,
            status="pending",
            notes=request.notes or f"Created from text: {request.text}"
        )
        db.add(parlay)
        db.flush()
        
        parlay.plays = created_plays
        db.commit()
        db.refresh(parlay)
        
        return {
            "parlay_id": parlay.parlay_id,
            "name": parlay.name,
            "total_odds": parlay.total_odds,
            "total_probability": parlay.total_probability,
            "total_legs": parlay.total_legs,
            "status": parlay.status,
            "matched_count": len(matched_bets),
            "parsed_count": len(parsed_bets),
            "plays": [
                {
                    "play_id": p.play_id,
                    "player_id": p.player_id,
                    "game_id": p.game_id,
                    "stat_type": p.stat_type,
                    "bet_line": p.bet_line
                }
                for p in created_plays
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/{parlay_id}/alternative")
async def generate_alternative_parlay(parlay_id: int):
    """Generate a safer alternative parlay with better odds."""
    db = SessionLocal()
    try:
        parlay = db.query(Parlay).filter(Parlay.parlay_id == parlay_id).first()
        
        if not parlay:
            raise HTTPException(status_code=404, detail="Parlay not found")
        
        # Get all plays from the parlay
        original_plays = parlay.plays
        
        if len(original_plays) < 2:
            raise HTTPException(status_code=400, detail="Parlay must have at least 2 plays")
        
        # Get target: we want a safer parlay (higher combined probability)
        # but try to maintain similar or better odds
        target_combined_prob = min(0.85, parlay.total_probability * 1.2)  # 20% safer, max 85%
        target_legs = len(original_plays)  # Keep same number of legs
        
        # Strategy: Find safer bets (75%+ individual probability) from today's games
        from app.models.prediction import Prediction
        from datetime import date, timedelta
        from sqlalchemy import or_
        
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        # Get all safe bets from today's and tomorrow's games
        safe_predictions = db.query(Prediction).join(
            Game, Prediction.game_id == Game.game_id
        ).filter(
            and_(
                Game.game_date >= today,
                Game.game_date <= tomorrow,
                Prediction.bet_type == 'safe',
                Prediction.safe_probability >= 0.75  # 75%+ probability
            )
        ).order_by(Prediction.safe_probability.desc()).limit(50).all()
        
        # Also get games from the original parlay to prioritize same games
        original_game_ids = {play.game_id for play in original_plays}
        
        # Score and rank predictions
        scored_predictions = []
        for pred in safe_predictions:
            score = pred.safe_probability
            
            # Bonus for same game as original parlay
            if pred.game_id in original_game_ids:
                score += 0.05
            
            # Bonus for same player (if we can find one)
            original_player_ids = {play.player_id for play in original_plays}
            if pred.player_id in original_player_ids:
                score += 0.03
            
            scored_predictions.append((score, pred))
        
        # Sort by score (highest first)
        scored_predictions.sort(key=lambda x: x[0], reverse=True)
        
        # Select best predictions to create safer parlay
        alternative_plays = []
        used_players = set()  # Diversify players
        used_games = set()  # Can use same games or different
        combined_prob = 1.0
        
        # First, try to improve existing plays with safer lines
        for play in original_plays:
            pred = db.query(Prediction).filter(
                and_(
                    Prediction.player_id == play.player_id,
                    Prediction.game_id == play.game_id,
                    Prediction.stat_type == play.stat_type
                )
            ).order_by(Prediction.created_at.desc()).first()
            
            if pred and pred.safe_probability and pred.safe_probability >= 0.75:
                # Use safer line for this player
                is_over = play.bet_line.startswith('Over')
                alt_line = pred.safe_line if is_over else (pred.distribution_mean + pred.distribution_std_dev)
                alt_bet_line = f"{'Over' if is_over else 'Under'} {alt_line:.1f}"
                
                # Check if play exists
                alt_play = db.query(UserPlay).filter(
                    and_(
                        UserPlay.player_id == play.player_id,
                        UserPlay.game_id == play.game_id,
                        UserPlay.stat_type == play.stat_type,
                        UserPlay.bet_line == alt_bet_line
                    )
                ).first()
                
                if not alt_play:
                    alt_play = UserPlay(
                        player_id=play.player_id,
                        game_id=play.game_id,
                        stat_type=play.stat_type,
                        bet_line=alt_bet_line,
                        notes=f"Safer alternative to play {play.play_id}",
                        predicted_min=int(pred.percentile_25) if pred.percentile_25 else None,
                        predicted_max=int(pred.percentile_85) if pred.percentile_85 else None,
                        likelihood_score=pred.safe_probability,
                        status="pending"
                    )
                    db.add(alt_play)
                    db.flush()
                
                alternative_plays.append(alt_play)
                used_players.add(play.player_id)
                used_games.add(play.game_id)
                combined_prob *= pred.safe_probability
            else:
                # Can't improve this play, try to find a better replacement
                # Look for a safer bet from the scored list
                for score, alt_pred in scored_predictions:
                    if (alt_pred.player_id not in used_players and 
                        alt_pred.safe_probability >= 0.75 and
                        len(alternative_plays) < target_legs):
                        
                        # Create play for this safer prediction
                        is_over = True  # Safe bets are usually Over
                        alt_bet_line = f"Over {alt_pred.safe_line:.1f}"
                        
                        alt_play = db.query(UserPlay).filter(
                            and_(
                                UserPlay.player_id == alt_pred.player_id,
                                UserPlay.game_id == alt_pred.game_id,
                                UserPlay.stat_type == alt_pred.stat_type,
                                UserPlay.bet_line == alt_bet_line
                            )
                        ).first()
                        
                        if not alt_play:
                            alt_play = UserPlay(
                                player_id=alt_pred.player_id,
                                game_id=alt_pred.game_id,
                                stat_type=alt_pred.stat_type,
                                bet_line=alt_bet_line,
                                notes=f"Safer alternative bet",
                                predicted_min=int(alt_pred.percentile_25) if alt_pred.percentile_25 else None,
                                predicted_max=int(alt_pred.percentile_85) if alt_pred.percentile_85 else None,
                                likelihood_score=alt_pred.safe_probability,
                                status="pending"
                            )
                            db.add(alt_play)
                            db.flush()
                        
                        alternative_plays.append(alt_play)
                        used_players.add(alt_pred.player_id)
                        used_games.add(alt_pred.game_id)
                        combined_prob *= alt_pred.safe_probability
                        break
        
        # If we don't have enough legs, add more safe bets
        while len(alternative_plays) < target_legs:
            for score, alt_pred in scored_predictions:
                if (alt_pred.player_id not in used_players and 
                    alt_pred.safe_probability >= 0.75):
                    
                    alt_bet_line = f"Over {alt_pred.safe_line:.1f}"
                    
                    alt_play = db.query(UserPlay).filter(
                        and_(
                            UserPlay.player_id == alt_pred.player_id,
                            UserPlay.game_id == alt_pred.game_id,
                            UserPlay.stat_type == alt_pred.stat_type,
                            UserPlay.bet_line == alt_bet_line
                        )
                    ).first()
                    
                    if not alt_play:
                        alt_play = UserPlay(
                            player_id=alt_pred.player_id,
                            game_id=alt_pred.game_id,
                            stat_type=alt_pred.stat_type,
                            bet_line=alt_bet_line,
                            notes=f"Safer alternative bet",
                            predicted_min=int(alt_pred.percentile_25) if alt_pred.percentile_25 else None,
                            predicted_max=int(alt_pred.percentile_85) if alt_pred.percentile_85 else None,
                            likelihood_score=alt_pred.safe_probability,
                            status="pending"
                        )
                        db.add(alt_play)
                        db.flush()
                    
                    alternative_plays.append(alt_play)
                    used_players.add(alt_pred.player_id)
                    combined_prob *= alt_pred.safe_probability
                    break
            else:
                # No more safe bets available
                break
        
        # Create alternative parlay
        total_probability = 1.0
        for play in alternative_plays:
            prob = play.likelihood_score if play.likelihood_score else 0.5
            total_probability *= prob
        
        if total_probability > 0:
            decimal_odds = 1.0 / total_probability
            if decimal_odds < 2.0:
                total_odds = -100 / (decimal_odds - 1)
            else:
                total_odds = 100 * (decimal_odds - 1)
        else:
            total_odds = None
        
        alt_parlay = Parlay(
            name=f"Alternative to {parlay.name or f'Parlay {parlay_id}'}",
            total_odds=total_odds,
            total_probability=total_probability,
            total_legs=len(alternative_plays),
            legs_hit=0,
            status="pending",
            notes=f"Alternative play generated from parlay {parlay_id}"
        )
        db.add(alt_parlay)
        db.flush()
        
        alt_parlay.plays = alternative_plays
        db.commit()
        db.refresh(alt_parlay)
        
        return {
            "parlay_id": alt_parlay.parlay_id,
            "name": alt_parlay.name,
            "total_odds": alt_parlay.total_odds,
            "total_probability": alt_parlay.total_probability,
            "total_legs": alt_parlay.total_legs,
            "status": alt_parlay.status,
            "original_parlay_id": parlay_id
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

