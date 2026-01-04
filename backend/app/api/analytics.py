"""
Analytics API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from app.database import SessionLocal
from app.models.team_position_defense import TeamPositionDefense
from app.models.player_team_matchup import PlayerTeamMatchup
from app.models.team import Team
from app.models.player import Player
from app.models.injury import Injury
from sqlalchemy import and_

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/team-defense/{team_id}")
async def get_team_defense(
    team_id: int,
    position: Optional[str] = Query(None, description="Filter by position"),
    season_id: Optional[int] = Query(None, description="Filter by season")
):
    """Get team defense stats by position."""
    db = SessionLocal()
    try:
        team = db.query(Team).filter(Team.team_id == team_id).first()
        
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        query = db.query(TeamPositionDefense).filter(
            TeamPositionDefense.team_id == team_id
        )
        
        if position:
            query = query.filter(TeamPositionDefense.position == position)
        
        if season_id:
            query = query.filter(TeamPositionDefense.season_id == season_id)
        
        defenses = query.all()
        
        return {
            "team_id": team_id,
            "team_name": team.name,
            "defense_stats": [
                {
                    "position": d.position,
                    "season_id": d.season_id,
                    "games_analyzed": d.games_analyzed,
                    "avg_points_allowed": d.avg_points_allowed,
                    "avg_rebounds_allowed": d.avg_rebounds_allowed,
                    "avg_assists_allowed": d.avg_assists_allowed,
                    "defensive_ranking": d.defensive_ranking
                }
                for d in defenses
            ]
        }
    finally:
        db.close()


@router.get("/matchup/{player_id}/{team_id}")
async def get_matchup(
    player_id: int,
    team_id: int,
    season_id: Optional[int] = Query(None, description="Filter by season")
):
    """Get player-team matchup history."""
    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.player_id == player_id).first()
        team = db.query(Team).filter(Team.team_id == team_id).first()
        
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        query = db.query(PlayerTeamMatchup).filter(
            and_(
                PlayerTeamMatchup.player_id == player_id,
                PlayerTeamMatchup.opponent_team_id == team_id
            )
        )
        
        if season_id:
            query = query.filter(PlayerTeamMatchup.season_id == season_id)
        
        matchups = query.all()
        
        return {
            "player_id": player_id,
            "player_name": player.name,
            "opponent_team_id": team_id,
            "opponent_team_name": team.name,
            "matchups": [
                {
                    "season_id": m.season_id,
                    "games_played": m.games_played,
                    "avg_points": m.avg_points,
                    "avg_rebounds": m.avg_rebounds,
                    "avg_assists": m.avg_assists,
                    "avg_minutes": m.avg_minutes,
                    "last_5_games_avg_points": m.last_5_games_avg_points
                }
                for m in matchups
            ]
        }
    finally:
        db.close()


@router.get("/injuries")
async def get_injuries(
    team_id: Optional[int] = Query(None, description="Filter by team")
):
    """Get current injuries."""
    db = SessionLocal()
    try:
        from app.services.injury_service import InjuryService
        
        service = InjuryService(db)
        
        if team_id:
            injuries = service.get_team_injuries(team_id)
        else:
            injuries = service.get_active_injuries()
        
        result = []
        for injury in injuries:
            player = db.query(Player).filter(Player.player_id == injury.player_id).first()
            result.append({
                "injury_id": injury.injury_id,
                "player_id": injury.player_id,
                "player_name": player.name if player else None,
                "status": injury.status,
                "injury_type": injury.injury_type,
                "injury_date": injury.injury_date.isoformat() if injury.injury_date else None,
                "expected_return_date": injury.expected_return_date.isoformat() if injury.expected_return_date else None,
                "description": injury.description
            })
        
        return result
    finally:
        db.close()


class CreateInjuryRequest(BaseModel):
    """Request to create an injury."""
    player_id: int
    status: str  # Out, Doubtful, Questionable, Probable
    injury_date: str  # ISO date string
    injury_type: Optional[str] = None
    description: Optional[str] = None
    expected_return_date: Optional[str] = None


@router.post("/injuries")
async def create_injury(request: CreateInjuryRequest):
    """Manually create an injury record."""
    db = SessionLocal()
    try:
        from app.services.injury_service import InjuryService
        from datetime import datetime
        
        service = InjuryService(db)
        
        # Parse dates
        injury_date = datetime.fromisoformat(request.injury_date.replace('Z', '+00:00')).date()
        expected_return_date = None
        if request.expected_return_date:
            expected_return_date = datetime.fromisoformat(request.expected_return_date.replace('Z', '+00:00')).date()
        
        # Verify player exists
        player = db.query(Player).filter(Player.player_id == request.player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        # Create injury
        injury = service.create_or_update_injury(
            player_id=request.player_id,
            status=request.status,
            injury_date=injury_date,
            injury_type=request.injury_type,
            expected_return_date=expected_return_date,
            description=request.description,
            source='manual'
        )
        
        return {
            "injury_id": injury.injury_id,
            "player_id": injury.player_id,
            "player_name": player.name,
            "status": injury.status,
            "injury_type": injury.injury_type,
            "injury_date": injury.injury_date.isoformat() if injury.injury_date else None,
            "expected_return_date": injury.expected_return_date.isoformat() if injury.expected_return_date else None,
            "description": injury.description
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

