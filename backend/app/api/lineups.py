"""
Lineup API endpoints.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from pydantic import BaseModel
from app.database import SessionLocal
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team
from app.models.lineup import Lineup
from app.services.lineup_service import LineupService

router = APIRouter(prefix="/api/lineups", tags=["lineups"])


class ConfirmLineupRequest(BaseModel):
    """Request to confirm a lineup."""
    game_id: int
    team_id: int
    starter_player_ids: List[int]
    positions: List[str] = None


@router.post("/confirm")
async def confirm_lineup(request: ConfirmLineupRequest):
    """Confirm a starting lineup for a game."""
    db = SessionLocal()
    try:
        service = LineupService(db)
        
        # Verify game exists
        game = db.query(Game).filter(Game.game_id == request.game_id).first()
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        # Verify team is in the game
        if game.home_team_id != request.team_id and game.away_team_id != request.team_id:
            raise HTTPException(status_code=400, detail="Team is not playing in this game")
        
        # Confirm lineup
        lineups = service.confirm_lineup(
            request.game_id,
            request.team_id,
            request.starter_player_ids,
            request.positions
        )
        
        # Get player names for response
        player_names = []
        for lineup in lineups:
            player = db.query(Player).filter(Player.player_id == lineup.player_id).first()
            player_names.append({
                "player_id": lineup.player_id,
                "player_name": player.name if player else f"Player {lineup.player_id}",
                "position": lineup.position
            })
        
        return {
            "success": True,
            "message": f"Lineup confirmed for game {request.game_id}",
            "lineup": player_names
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/game/{game_id}")
async def get_game_lineups(game_id: int):
    """Get lineups for a game (starters and bench)."""
    db = SessionLocal()
    try:
        # Get all lineups for this game (starters and bench)
        all_lineups = db.query(Lineup).filter(Lineup.game_id == game_id).all()
        
        # Organize by team
        result = {}
        for lineup in all_lineups:
            team_id = lineup.team_id
            if team_id not in result:
                team = db.query(Team).filter(Team.team_id == team_id).first()
                result[team_id] = {
                    "team_id": team_id,
                    "team_name": team.name if team else None,
                    "team_abbreviation": team.abbreviation if team else None,
                    "is_confirmed": False,
                    "starters": [],
                    "bench": []
                }
            
            player = db.query(Player).filter(Player.player_id == lineup.player_id).first()
            player_data = {
                "player_id": lineup.player_id,
                "player_name": player.name if player else f"Player {lineup.player_id}",
                "position": lineup.position,
                "confirmed_at": lineup.confirmed_at.isoformat() if lineup.confirmed_at else None
            }
            
            if lineup.is_starter:
                result[team_id]["starters"].append(player_data)
            else:
                result[team_id]["bench"].append(player_data)
        
        # Mark as confirmed if we have at least 3 starters
        for team_id in result:
            result[team_id]["is_confirmed"] = len(result[team_id]["starters"]) >= 3
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/game/{game_id}/team/{team_id}/confirmed")
async def is_lineup_confirmed(game_id: int, team_id: int):
    """Check if lineup is confirmed for a team in a game."""
    db = SessionLocal()
    try:
        service = LineupService(db)
        is_confirmed = service.is_lineup_confirmed(game_id, team_id)
        
        return {
            "game_id": game_id,
            "team_id": team_id,
            "is_confirmed": is_confirmed
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/collect")
async def collect_lineups(
    game_date: Optional[str] = None,
    days_ahead: int = 1
):
    """
    Collect lineups for games on a specific date (or today if not specified).
    
    Args:
        game_date: Date to collect lineups for (YYYY-MM-DD format). If None, uses today.
        days_ahead: Number of days ahead to collect (default: 1, meaning today and tomorrow)
    """
    from datetime import date, timedelta
    from app.scrapers.lineup_scraper import LineupScraper
    
    db = SessionLocal()
    try:
        scraper = LineupScraper(db_session=db)
        
        if game_date:
            try:
                from datetime import datetime
                target_date = datetime.strptime(game_date, '%Y-%m-%d').date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        else:
            target_date = date.today()
        
        results = {}
        total_collected = 0
        
        # Collect for target date and next N days
        for day_offset in range(days_ahead + 1):
            current_date = target_date + timedelta(days=day_offset)
            result = scraper.collect_lineups_for_date(current_date)
            results[current_date.isoformat()] = result
            total_collected += result.get('total', 0)
        
        return {
            "success": True,
            "message": f"Collected {total_collected} lineups",
            "results": results,
            "total_collected": total_collected
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting lineups: {str(e)}")
    finally:
        db.close()


@router.post("/game/{game_id}/infer")
async def infer_lineups_from_stats(game_id: int):
    """Infer lineups from box score stats (for finished games)."""
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        if game.game_status != 'finished':
            raise HTTPException(status_code=400, detail="Can only infer lineups for finished games")
        
        service = LineupService(db)
        inferred = service.infer_lineup_from_game_stats(game_id)
        
        # Save inferred lineups
        saved_count = 0
        for team_id, lineup_list in inferred.items():
            for lineup in lineup_list:
                # Check if already exists
                existing = db.query(Lineup).filter(
                    and_(
                        Lineup.game_id == game_id,
                        Lineup.team_id == team_id,
                        Lineup.player_id == lineup.player_id
                    )
                ).first()
                if not existing:
                    db.add(lineup)
                    saved_count += 1
        
        db.commit()
        
        # Get team names for response
        result = {}
        for team_id, lineup_list in inferred.items():
            team = db.query(Team).filter(Team.team_id == team_id).first()
            result[team_id] = {
                "team_id": team_id,
                "team_name": team.name if team else None,
                "team_abbreviation": team.abbreviation if team else None,
                "starters": []
            }
            for lineup in lineup_list:
                player = db.query(Player).filter(Player.player_id == lineup.player_id).first()
                result[team_id]["starters"].append({
                    "player_id": lineup.player_id,
                    "player_name": player.name if player else f"Player {lineup.player_id}",
                    "position": lineup.position
                })
        
        return {
            "success": True,
            "message": f"Inferred {saved_count} lineup entries for game {game_id}",
            "lineups": result
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

