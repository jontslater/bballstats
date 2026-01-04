"""
Player API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import SessionLocal
from app.models.player import Player
from app.models.team import Team
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from sqlalchemy import func, and_
from app.services.player_team_sync import PlayerTeamSyncService

router = APIRouter(prefix="/api/players", tags=["players"])


@router.get("")
async def get_players(
    team_id: Optional[int] = Query(None, description="Filter by team"),
    position: Optional[str] = Query(None, description="Filter by position"),
    limit: int = Query(100, description="Maximum number of results")
):
    """Get list of players."""
    db = SessionLocal()
    try:
        query = db.query(Player)
        
        if team_id:
            query = query.filter(Player.current_team_id == team_id)
        
        if position:
            query = query.filter(Player.position == position)
        
        players = query.limit(limit).all()
        
        # Enrich with team names
        result = []
        for player in players:
            team = db.query(Team).filter(Team.team_id == player.current_team_id).first()
            result.append({
                "player_id": player.player_id,
                "name": player.name,
                "position": player.position,
                "height": player.height,
                "weight": player.weight,
                "current_team_id": player.current_team_id,
                "current_team_name": team.name if team else None,
                "current_team_abbreviation": team.abbreviation if team else None
            })
        
        return result
    finally:
        db.close()


@router.get("/{player_id}")
async def get_player(player_id: int):
    """Get player details."""
    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.player_id == player_id).first()
        
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        team = db.query(Team).filter(Team.team_id == player.current_team_id).first()
        
        return {
            "player_id": player.player_id,
            "name": player.name,
            "position": player.position,
            "height": player.height,
            "weight": player.weight,
            "birth_date": player.birth_date.isoformat() if player.birth_date else None,
            "current_team": {
                "team_id": player.current_team_id,
                "name": team.name if team else None,
                "abbreviation": team.abbreviation if team else None
            }
        }
    finally:
        db.close()


@router.get("/{player_id}/stats")
async def get_player_stats(
    player_id: int,
    season_id: Optional[int] = Query(None, description="Filter by season"),
    limit: int = Query(50, description="Maximum number of games")
):
    """Get player statistics."""
    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.player_id == player_id).first()
        
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        
        query = db.query(PlayerGameStat).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.game_status == 'finished'
            )
        )
        
        if season_id:
            query = query.filter(Game.season_id == season_id)
        
        stats = query.order_by(Game.game_date.desc()).limit(limit).all()
        
        # Calculate averages
        if stats:
            avg_points = sum(s.points for s in stats) / len(stats)
            avg_rebounds = sum(s.rebounds for s in stats) / len(stats)
            avg_assists = sum(s.assists for s in stats) / len(stats)
            avg_minutes = sum(s.minutes_played for s in stats) / len(stats)
        else:
            avg_points = avg_rebounds = avg_assists = avg_minutes = 0
        
        return {
            "player_id": player_id,
            "player_name": player.name,
            "games_played": len(stats),
            "averages": {
                "points": round(avg_points, 2),
                "rebounds": round(avg_rebounds, 2),
                "assists": round(avg_assists, 2),
                "minutes": round(avg_minutes, 2)
            },
            "recent_games": [
                {
                    "game_id": s.game_id,
                    "game_date": db.query(Game).filter(Game.game_id == s.game_id).first().game_date.isoformat(),
                    "points": s.points,
                    "rebounds": s.rebounds,
                    "assists": s.assists,
                    "minutes": s.minutes_played
                }
                for s in stats[:10]
            ]
        }
    finally:
        db.close()


@router.post("/sync-teams")
async def sync_player_teams(
    days_back: int = Query(30, description="Number of days to look back for recent games")
):
    """Sync all player team assignments from recent game stats."""
    db = SessionLocal()
    try:
        service = PlayerTeamSyncService(db)
        result = service.sync_all_players(days_back=days_back)
        return {
            "success": True,
            "message": f"Synced {result['updated']} players, {result['unchanged']} unchanged, {result['errors']} errors",
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/team-mismatches")
async def get_team_mismatches(
    days_back: int = Query(7, description="Number of days to look back")
):
    """Find players whose team assignment doesn't match recent game stats."""
    db = SessionLocal()
    try:
        service = PlayerTeamSyncService(db)
        mismatches = service.find_team_mismatches(days_back=days_back)
        return {
            "mismatches": mismatches,
            "count": len(mismatches)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

