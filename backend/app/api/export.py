"""
Export API endpoints.
"""
from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
import csv
import io
from app.database import SessionLocal
from app.models.prediction import Prediction
from app.models.user_play import UserPlay
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team
from sqlalchemy import and_

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/picks/{game_date}")
async def export_picks(game_date: date):
    """Export picks for a date as CSV."""
    db = SessionLocal()
    try:
        games = db.query(Game).filter(Game.game_date == game_date).all()
        game_ids = [g.game_id for g in games]
        
        predictions = db.query(Prediction).filter(
            and_(
                Prediction.game_id.in_(game_ids),
                Prediction.bet_type.in_(['safe', 'standard', 'long_shot'])
            )
        ).all()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            'Player', 'Team', 'Stat Type', 'Bet Type', 'Line', 'Probability',
            'Mean', 'Std Dev', 'Game Date', 'Opponent'
        ])
        
        # Data rows
        for pred in predictions:
            player = db.query(Player).filter(Player.player_id == pred.player_id).first()
            game = db.query(Game).filter(Game.game_id == pred.game_id).first()
            
            if not player or not game:
                continue
            
            # Determine opponent
            is_home = (game.home_team_id == player.current_team_id)
            opponent_id = game.away_team_id if is_home else game.home_team_id
            opponent = db.query(Team).filter(Team.team_id == opponent_id).first()
            
            # Get line based on bet type
            if pred.bet_type == 'safe':
                line = pred.safe_line
                prob = pred.safe_probability
            elif pred.bet_type == 'standard':
                line = pred.standard_line
                prob = pred.standard_probability
            else:
                line = pred.long_shot_line
                prob = pred.long_shot_probability
            
            team = db.query(Team).filter(Team.team_id == player.current_team_id).first()
            
            writer.writerow([
                player.name,
                team.abbreviation if team else '',
                pred.stat_type,
                pred.bet_type,
                line,
                f"{prob:.1%}",
                pred.distribution_mean,
                pred.distribution_std_dev,
                game.game_date.isoformat(),
                opponent.abbreviation if opponent else ''
            ])
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=picks_{game_date}.csv"}
        )
    finally:
        db.close()


@router.get("/plays")
async def export_plays():
    """Export all plays as CSV."""
    db = SessionLocal()
    try:
        plays = db.query(UserPlay).order_by(UserPlay.created_at.desc()).all()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            'Player', 'Game Date', 'Stat Type', 'Bet Line', 'Status',
            'Predicted Min', 'Predicted Max', 'Actual Result', 'Notes'
        ])
        
        # Data rows
        for play in plays:
            player = db.query(Player).filter(Player.player_id == play.player_id).first()
            game = db.query(Game).filter(Game.game_id == play.game_id).first()
            
            writer.writerow([
                player.name if player else '',
                game.game_date.isoformat() if game else '',
                play.stat_type,
                play.bet_line,
                play.status,
                play.predicted_min,
                play.predicted_max,
                play.actual_result or '',
                play.notes or ''
            ])
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=plays.csv"}
        )
    finally:
        db.close()


@router.get("/predictions/{game_id}")
async def export_predictions(game_id: int):
    """Export predictions for a game as CSV."""
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.game_id == game_id).first()
        
        if not game:
            return Response(content="Game not found", status_code=404)
        
        predictions = db.query(Prediction).filter(Prediction.game_id == game_id).all()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            'Player', 'Stat Type', 'Mean', 'Std Dev',
            'Safe Line', 'Safe Prob', 'Standard Line', 'Standard Prob',
            'Long Shot Line', 'Long Shot Prob', 'Bet Type', 'Confidence'
        ])
        
        # Data rows
        for pred in predictions:
            player = db.query(Player).filter(Player.player_id == pred.player_id).first()
            
            writer.writerow([
                player.name if player else '',
                pred.stat_type,
                pred.distribution_mean,
                pred.distribution_std_dev,
                pred.safe_line,
                f"{pred.safe_probability:.1%}",
                pred.standard_line,
                f"{pred.standard_probability:.1%}",
                pred.long_shot_line,
                f"{pred.long_shot_probability:.1%}",
                pred.bet_type,
                pred.confidence_level
            ])
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=predictions_game_{game_id}.csv"}
        )
    finally:
        db.close()


