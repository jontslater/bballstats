"""
Analyze API endpoints - For analyzing custom bet lines
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from pydantic import BaseModel
from app.database import SessionLocal
from app.models.player import Player
from app.models.game import Game
from app.models.prediction import Prediction
from scipy.stats import norm
from datetime import date, datetime

router = APIRouter(prefix="/api/analyze", tags=["analyze"])


class AnalyzeBetRequest(BaseModel):
    """Request to analyze a custom bet line."""
    player_id: int
    game_id: int
    stat_type: str  # points, rebounds, assists
    bet_line: float  # The line value (e.g., 6.0)
    bet_type: str  # "Over" or "Under"


@router.post("/bet")
async def analyze_bet(request: AnalyzeBetRequest):
    """Analyze a custom bet line and return likelihood."""
    db = SessionLocal()
    try:
        # Get the prediction for this player/game/stat
        prediction = db.query(Prediction).filter(
            Prediction.player_id == request.player_id,
            Prediction.game_id == request.game_id,
            Prediction.stat_type == request.stat_type
        ).first()
        
        if not prediction:
            raise HTTPException(
                status_code=404, 
                detail="No prediction found for this player/game/stat. Generate predictions first."
            )
        
        # Calculate probability using the distribution
        dist = norm(loc=prediction.distribution_mean, scale=prediction.distribution_std_dev)
        
        if request.bet_type.lower() == "over":
            probability = float(1.0 - dist.cdf(request.bet_line))
        else:  # Under
            probability = float(dist.cdf(request.bet_line))
        
        # Get player and game info
        player = db.query(Player).filter(Player.player_id == request.player_id).first()
        game = db.query(Game).filter(Game.game_id == request.game_id).first()
        
        # Calculate alternative suggestions
        alternatives = []
        
        # Suggest safer alternative (higher probability)
        if request.bet_type.lower() == "over":
            # Try lower line for higher probability
            for alt_line in [request.bet_line - 1.0, request.bet_line - 0.5]:
                if alt_line > 0:
                    alt_prob = float(1.0 - dist.cdf(alt_line))
                    if alt_prob > probability and alt_prob >= 0.60:
                        alternatives.append({
                            "bet_line": f"Over {alt_line:.1f}",
                            "probability": round(alt_prob, 3),
                            "reason": "Safer option"
                        })
                        break
        
        # Suggest better value (similar probability but better line)
        if request.bet_type.lower() == "over":
            # Try slightly higher line with similar probability
            for alt_line in [request.bet_line + 0.5, request.bet_line + 1.0]:
                alt_prob = float(1.0 - dist.cdf(alt_line))
                if 0.45 <= alt_prob <= probability + 0.05:  # Similar probability
                    alternatives.append({
                        "bet_line": f"Over {alt_line:.1f}",
                        "probability": round(alt_prob, 3),
                        "reason": "Better value"
                    })
                    break
        
        # Get the standard bet lines for comparison
        safe_line = prediction.safe_line if prediction.safe_line else None
        standard_line = prediction.standard_line if prediction.standard_line else None
        long_shot_line = prediction.long_shot_line if prediction.long_shot_line else None
        
        return {
            "player_name": player.name if player else f"Player {request.player_id}",
            "game_id": request.game_id,
            "stat_type": request.stat_type,
            "bet_line": f"{request.bet_type} {request.bet_line:.1f}",
            "probability": round(probability, 3),
            "mean": round(prediction.distribution_mean, 2),
            "std_dev": round(prediction.distribution_std_dev, 2),
            "confidence_level": prediction.confidence_level,
            "volatility_level": prediction.volatility_level,
            "reasoning": prediction.reasoning,
            "alternatives": alternatives,
            "suggested_lines": {
                "safe": safe_line,
                "standard": standard_line,
                "long_shot": long_shot_line
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


class AnalyzeParlayRequest(BaseModel):
    """Request to analyze a parlay."""
    legs: List[Dict]  # List of {player_id, game_id, stat_type, bet_line, bet_type}


@router.post("/parlay")
async def analyze_parlay(request: AnalyzeParlayRequest):
    """Analyze a parlay with multiple legs."""
    db = SessionLocal()
    try:
        if len(request.legs) < 2:
            raise HTTPException(status_code=400, detail="Parlay must have at least 2 legs")
        
        leg_analyses = []
        total_probability = 1.0
        
        for leg in request.legs:
            player_id = leg.get('player_id')
            game_id = leg.get('game_id')
            stat_type = leg.get('stat_type')
            bet_line = leg.get('bet_line')
            bet_type = leg.get('bet_type', 'Over')
            
            if not all([player_id, game_id, stat_type, bet_line]):
                continue
            
            # Get prediction
            prediction = db.query(Prediction).filter(
                Prediction.player_id == player_id,
                Prediction.game_id == game_id,
                Prediction.stat_type == stat_type
            ).first()
            
            if not prediction:
                leg_analyses.append({
                    "player_name": f"Player {player_id}",
                    "bet_line": f"{bet_type} {bet_line:.1f}",
                    "probability": None,
                    "error": "No prediction found"
                })
                continue
            
            # Calculate probability
            dist = norm(loc=prediction.distribution_mean, scale=prediction.distribution_std_dev)
            if bet_type.lower() == "over":
                probability = float(1.0 - dist.cdf(bet_line))
            else:
                probability = float(dist.cdf(bet_line))
            
            player = db.query(Player).filter(Player.player_id == player_id).first()
            
            leg_analyses.append({
                "player_name": player.name if player else f"Player {player_id}",
                "bet_line": f"{bet_type} {bet_line:.1f}",
                "probability": round(probability, 3),
                "mean": round(prediction.distribution_mean, 2),
                "std_dev": round(prediction.distribution_std_dev, 2)
            })
            
            if probability:
                total_probability *= probability
        
        # Calculate combined odds
        if total_probability > 0:
            decimal_odds = 1.0 / total_probability
            american_odds = (decimal_odds - 1) * 100
            if american_odds >= 0:
                odds_display = f"+{int(round(american_odds))}"
            else:
                odds_display = f"{int(round(american_odds))}"
        else:
            odds_display = "N/A"
        
        # Overall assessment
        if total_probability >= 0.50:
            assessment = "Strong parlay - Good chance of hitting"
        elif total_probability >= 0.30:
            assessment = "Moderate parlay - Reasonable chance"
        elif total_probability >= 0.15:
            assessment = "Long shot parlay - Lower probability but possible"
        else:
            assessment = "Very long shot - Low probability"
        
        return {
            "legs": leg_analyses,
            "combined_probability": round(total_probability, 4),
            "combined_odds": odds_display,
            "overall_assessment": assessment
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/search-players")
async def search_players(
    query: str = Query(..., description="Player name search query"),
    limit: int = Query(20, description="Maximum number of results")
):
    """Search for players by name."""
    db = SessionLocal()
    try:
        players = db.query(Player).filter(
            Player.name.ilike(f"%{query}%")
        ).limit(limit).all()
        
        return [
            {
                "player_id": p.player_id,
                "name": p.name,
                "team": p.current_team_id,  # You might want to join with Team table
                "position": p.position
            }
            for p in players
        ]
    finally:
        db.close()


@router.get("/player-games")
async def get_player_games(
    player_id: int,
    game_date: Optional[str] = Query(None, description="Filter by game date (YYYY-MM-DD)")
):
    """Get upcoming games for a player."""
    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.player_id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        # Get player's team
        team_id = player.current_team_id
        if not team_id:
            raise HTTPException(status_code=400, detail="Player has no current team")
        
        # Get games for the team
        from datetime import date as date_type
        today = date_type.today()
        
        query = db.query(Game).filter(
            (Game.home_team_id == team_id) | (Game.away_team_id == team_id),
            Game.game_date >= today
        )
        
        if game_date:
            try:
                parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
                query = query.filter(Game.game_date == parsed_date)
            except ValueError:
                pass
        
        games = query.order_by(Game.game_date).limit(10).all()
        
        from app.models.team import Team
        
        result = []
        for game in games:
            if game.home_team_id == team_id:
                opponent_team_id = game.away_team_id
            else:
                opponent_team_id = game.home_team_id
            
            opponent_team = db.query(Team).filter(Team.team_id == opponent_team_id).first()
            
            result.append({
                "game_id": game.game_id,
                "game_date": game.game_date.isoformat() if game.game_date else None,
                "opponent": opponent_team.abbreviation if opponent_team else "Unknown",
                "home_away": "Home" if game.home_team_id == team_id else "Away"
            })
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

