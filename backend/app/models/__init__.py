"""
Database models for NBA Betting Analytics Platform.

Import all models here so they're registered with SQLAlchemy.
"""

from .team import Team
from .season import Season
from .player import Player
from .game import Game
from .player_game_stat import PlayerGameStat
from .injury import Injury
from .team_position_defense import TeamPositionDefense
from .player_team_matchup import PlayerTeamMatchup
from .injury_impact_history import InjuryImpactHistory
from .prediction import Prediction, ValueLadder, HistoricalSuggestedBet, HistoricalParlay, HistoricalParlayLeg
from .game_schedule import GameSchedule
from .user_play import UserPlay
from .lineup import Lineup
from .betting_line import BettingLine
from .parlay import Parlay
from .poor_mans_bet import PoorMansBetChallenge, PoorMansBetDay

__all__ = [
    "Team",
    "Season",
    "Player",
    "Game",
    "PlayerGameStat",
    "Injury",
    "TeamPositionDefense",
    "PlayerTeamMatchup",
    "InjuryImpactHistory",
    "Prediction",
    "ValueLadder",
    "HistoricalSuggestedBet",
    "HistoricalParlay",
    "HistoricalParlayLeg",
    "GameSchedule",
    "UserPlay",
    "Lineup",
    "BettingLine",
    "Parlay",
    "PoorMansBetChallenge",
    "PoorMansBetDay",
]

