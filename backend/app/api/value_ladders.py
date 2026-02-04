"""
Value Ladders API endpoints.
Provides ladder betting recommendations based on prediction analysis.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from app.services.value_ladder_service import ValueLadderService
from app.models.prediction import ValueLadder
from app.models.player import Player
from app.models.game import Game
from app.models.team import Team
from sqlalchemy.orm import joinedload
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/value-ladders", tags=["value-ladders"])


@router.get("/recommendations")
async def get_value_ladder_recommendations(
    sport: str = Query('NBA', description="Sport type (NBA or NFL)"),
    days_ahead: int = Query(1, description="Number of days to look ahead (default 1 for today's games)"),
    min_steps: int = Query(3, description="Minimum number of ladder steps")
):
    """
    Get value ladder recommendations from database.

    Returns pre-computed ladders generated during prediction creation.
    Focuses on today's games by default.
    """
    from app.database import SessionLocal
    from datetime import date, timedelta

    db = SessionLocal()
    try:
        # Focus on today's games by default, but allow looking ahead
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)

        # Get ladders from database - prioritize today's games
        # Join Game table explicitly to filter by date
        from sqlalchemy import and_
        ladders_query = db.query(ValueLadder).join(
            Game, ValueLadder.game_id == Game.game_id
        ).options(
            joinedload(ValueLadder.player).joinedload(Player.team),
            joinedload(ValueLadder.game).joinedload(Game.home_team),
            joinedload(ValueLadder.game).joinedload(Game.away_team)
        ).filter(
            and_(
                ValueLadder.sport == sport,
                Game.game_date >= start_date,
                Game.game_date <= end_date
            )
        ).order_by(
            Game.game_date.asc(),  # Today's games first
            ValueLadder.expected_value_total.desc()
        ).limit(20)

        ladders_data = []
        for ladder in ladders_query:
            player = ladder.player
            game = ladder.game

            if player and game:
                # Determine opponent - be very defensive about this
                opponent_name = 'UNK'

                try:
                    player_team_id = player.team_id if player.team else None

                    if player_team_id and game.home_team_id == player_team_id:
                        # Player is home team, opponent is away team
                        opponent_name = game.away_team.abbreviation if game.away_team else 'AWAY'
                    elif player_team_id and game.away_team_id == player_team_id:
                        # Player is away team, opponent is home team
                        opponent_name = game.home_team.abbreviation if game.home_team else 'HOME'
                    else:
                        # Player team doesn't match game teams or player has no team - use game info
                        home_abbrev = game.home_team.abbreviation if game.home_team else 'HOME'
                        away_abbrev = game.away_team.abbreviation if game.away_team else 'AWAY'
                        opponent_name = f"{away_abbrev}@{home_abbrev}"
                except Exception as e:
                    logger.error(f"Error determining opponent for player {player.name}: {e}")
                    opponent_name = 'UNK'

                logger.info(f"Ladder for {player.name} ({player.team.abbreviation if player.team else 'NO_TEAM'}) vs {opponent_name} on {game.game_date}")

                ladder_dict = {
                    'player_id': ladder.player_id,
                    'player_name': player.name,
                    'team_abbrev': player.team.abbreviation if player.team else 'UNK',
                    'opponent_abbrev': opponent_name,
                    'game_date': game.game_date.isoformat(),
                    'stat_type': ladder.stat_type,
                    'steps': [
                        {
                            'line': ladder.normal_performance,
                            'confidence': ladder.confidence_normal,
                            'expected_value': round(ladder.confidence_normal * 0.01 * 1.0 + (1 - ladder.confidence_normal * 0.01) * (-1.1), 3),
                            'step_number': 1
                        },
                        {
                            'line': ladder.midpoint_performance,
                            'confidence': ladder.confidence_midpoint,
                            'expected_value': round(ladder.confidence_midpoint * 0.01 * 1.0 + (1 - ladder.confidence_midpoint * 0.01) * (-1.1), 3),
                            'step_number': 2
                        },
                        {
                            'line': ladder.exceptional_performance,
                            'confidence': ladder.confidence_exceptional,
                            'expected_value': round(ladder.confidence_exceptional * 0.01 * 1.0 + (1 - ladder.confidence_exceptional * 0.01) * (-1.1), 3),
                            'step_number': 3
                        }
                    ],
                    'expected_value': ladder.expected_value_total,
                    'confidence_score': ladder.confidence_normal / 100,
                    'historical_games': 15,  # Placeholder
                    'avg_points': ladder.normal_performance,  # Use normal as baseline
                    'value_edge': 0.05
                }
                ladders_data.append(ladder_dict)

        logger.info(f"Retrieved {len(ladders_data)} value ladders from database for {sport}")

        return {
            "ladders": ladders_data,
            "total_count": len(ladders_data),
            "sport": sport,
            "days_ahead": days_ahead,
            "source": "database"
        }

    except Exception as e:
        logger.error(f"Error retrieving value ladders: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve value ladders: {str(e)}")
    finally:
        db.close()


@router.get("/player/{player_id}")
async def get_player_value_ladders(
    player_id: int,
    sport: str = Query('NBA', description="Sport type (NBA or NFL)"),
    days_ahead: int = Query(14, description="Number of days to look ahead")
):
    """
    Get value ladder recommendations for a specific player.
    """
    try:
        service = ValueLadderService()

        # Get all ladders and filter by player
        all_ladders = service.generate_value_ladders(sport=sport, days_ahead=days_ahead)
        player_ladders = [l for l in all_ladders if l.get('player_id') == player_id]

        return {
            "player_id": player_id,
            "ladders": player_ladders,
            "total_count": len(player_ladders)
        }

    except Exception as e:
        logger.error(f"Error getting player ladders: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get player ladders: {str(e)}")