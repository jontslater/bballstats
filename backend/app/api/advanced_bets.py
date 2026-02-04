"""
Advanced Bets API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import SessionLocal
from app.services.advanced_bet_generator import AdvancedBetGenerator
from app.models.game import Game
from app.models.team import Team

router = APIRouter(prefix="/api/advanced-bets", tags=["advanced-bets"])


@router.get("/game/{game_id}")
async def get_advanced_bets_for_game(
    game_id: int,
    limit_per_type: int = Query(5, description="Maximum bets per type"),
    sport: str = Query('NBA', description="Sport type (NBA or NFL)")
):
    """Get all advanced bet types for a game."""
    db = SessionLocal()
    try:
        generator = AdvancedBetGenerator(db, sport)
        bets = generator.get_all_advanced_bets_for_game(game_id, limit_per_type)
        return bets
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/combo-props/{game_id}/{player_id}")
async def get_combo_props(
    game_id: int,
    player_id: int,
    combo_type: str = Query("points_rebounds", description="Combo type: points_rebounds, points_assists, rebounds_assists")
):
    """Get combo prop bets for a player."""
    db = SessionLocal()
    try:
        generator = AdvancedBetGenerator(db)
        bets = generator.generate_combo_props(game_id, player_id, combo_type)
        return bets
    finally:
        db.close()


@router.get("/milestone-props/{game_id}/{player_id}")
async def get_milestone_props(
    game_id: int,
    player_id: int
):
    """Get milestone prop bets for a player."""
    db = SessionLocal()
    try:
        generator = AdvancedBetGenerator(db)
        bets = generator.generate_milestone_props(game_id, player_id)
        return bets
    finally:
        db.close()


@router.get("/player-vs-player/{game_id}/{player1_id}/{player2_id}")
async def get_player_vs_player(
    game_id: int,
    player1_id: int,
    player2_id: int,
    stat_type: str = Query("points", description="Stat type: points, rebounds, assists")
):
    """Get player vs player prop."""
    db = SessionLocal()
    try:
        generator = AdvancedBetGenerator(db)
        prop = generator.generate_player_vs_player_props(game_id, player1_id, player2_id, stat_type)
        if not prop:
            raise HTTPException(status_code=404, detail="Player vs player prop not available")
        return prop
    finally:
        db.close()


@router.get("/alternate-lines/{game_id}/{player_id}/{stat_type}")
async def get_alternate_lines(
    game_id: int,
    player_id: int,
    stat_type: str
):
    """Get alternate line options for a player/stat."""
    db = SessionLocal()
    try:
        generator = AdvancedBetGenerator(db)
        lines = generator.generate_alternate_lines(game_id, player_id, stat_type)
        return lines
    finally:
        db.close()


@router.get("/performance-brackets/{game_id}/{player_id}/{stat_type}")
async def get_performance_brackets(
    game_id: int,
    player_id: int,
    stat_type: str
):
    """Get performance bracket bets for a player/stat."""
    db = SessionLocal()
    try:
        generator = AdvancedBetGenerator(db)
        brackets = generator.generate_performance_brackets(game_id, player_id, stat_type)
        return brackets
    finally:
        db.close()


@router.get("/team-totals/{game_id}/{team_id}")
async def get_team_totals(
    game_id: int,
    team_id: int,
    stat_type: str = Query("points", description="Stat type: points, rebounds, assists")
):
    """Get team total props."""
    db = SessionLocal()
    try:
        generator = AdvancedBetGenerator(db)
        team_total = generator.generate_team_total_props(game_id, team_id, stat_type)
        if not team_total:
            raise HTTPException(status_code=404, detail="Team total prop not available")
        return team_total
    finally:
        db.close()


@router.get("/date/{game_date}")
async def get_advanced_bets_for_date(
    game_date: str,
    limit_per_type: int = Query(10, description="Maximum bets per type per game")
):
    """Get all advanced bet types for all games on a date."""
    db = SessionLocal()
    try:
        from datetime import datetime
        parsed_date = datetime.strptime(game_date, '%Y-%m-%d').date()
        
        generator = AdvancedBetGenerator(db)
        
        # Get all games for the date
        games = db.query(Game).filter(Game.game_date == parsed_date).all()
        
        result = {
            'game_date': game_date,
            'games': []
        }
        
        for game in games:
            game_bets = generator.get_all_advanced_bets_for_game(game.game_id, limit_per_type)
            
            # Get game info
            home_team = db.query(Team).filter(Team.team_id == game.home_team_id).first()
            away_team = db.query(Team).filter(Team.team_id == game.away_team_id).first()
            
            result['games'].append({
                'game_id': game.game_id,
                'home_team': home_team.abbreviation if home_team else None,
                'away_team': away_team.abbreviation if away_team else None,
                'home_team_name': home_team.name if home_team else None,
                'away_team_name': away_team.name if away_team else None,
                **game_bets
            })
        
        return result
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

