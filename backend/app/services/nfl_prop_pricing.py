"""
Price a single NFL player prop against a sportsbook line (e.g. FanDuel via The Odds API).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Game, Player
from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.services.distribution_engine import DistributionEngine
from app.services.nfl_data import american_break_even_odds
from app.services.nfl_position_priors import role_for_position
from app.services.prediction_service import PredictionService

# The Odds API market keys → internal stat_type
ODDS_API_MARKET_MAP: Dict[str, str] = {
    "player_pass_yds": "passing_yards",
    "player_pass_tds": "passing_tds",
    "player_pass_completions": "completions",
    "player_pass_attempts": "attempts",
    "player_rush_yds": "rushing_yards",
    "player_rush_attempts": "rushing_attempts",
    "player_receptions": "receptions",
    "player_reception_yds": "receiving_yards",
    "player_anytime_td": "anytime_td",
}


@dataclass
class PropPriceResult:
    player_name: str
    stat_type: str
    line: float
    model_probability: float
    calibrated_probability: float
    break_even_american_odds: Optional[int]
    sportsbook_american_odds: Optional[int]
    implied_probability: Optional[float]
    edge: Optional[float]
    sample_size: int
    player_mean: float
    player_std: float


def american_to_implied(odds: int) -> float:
    if odds == 0:
        return 0.5
    if odds < 0:
        return (-odds) / ((-odds) + 100.0)
    return 100.0 / (odds + 100.0)


def parse_american_odds(odds_str: str) -> int:
    s = str(odds_str).strip().replace("−", "-")
    if s.startswith("+"):
        s = s[1:]
    return int(round(float(s)))


class NFLPropPricingService:
    def __init__(self, db: Session):
        self.db = db
        self.dist = DistributionEngine(db)
        self.calc = CalibratedProbabilityCalculator(sport="NFL")
        self.pred_service = PredictionService(db, sport="NFL")

    def resolve_player(self, player_name: str, team_abbrev: Optional[str] = None) -> Optional[Player]:
        q = self.db.query(Player).filter(Player.sport == "NFL", Player.name.ilike(player_name))
        if team_abbrev:
            from app.models import Team

            team = self.db.query(Team).filter(
                Team.sport == "NFL", Team.abbreviation == team_abbrev.upper()
            ).first()
            if team:
                q = q.filter(Player.current_team_id == team.team_id)
        exact = q.first()
        if exact:
            return exact
        return self.db.query(Player).filter(
            Player.sport == "NFL", Player.name.ilike(f"%{player_name}%")
        ).first()

    def price_prop(
        self,
        player_name: str,
        stat_type: str,
        line: float,
        sportsbook_odds: Optional[str] = None,
        game_id: Optional[int] = None,
        team_abbrev: Optional[str] = None,
    ) -> PropPriceResult:
        market_stat = ODDS_API_MARKET_MAP.get(stat_type, stat_type)
        player = self.resolve_player(player_name, team_abbrev)
        if not player:
            raise ValueError(f"NFL player not found: {player_name}")

        if game_id is None:
            from datetime import date, timedelta
            from sqlalchemy import or_

            today = date.today()
            game = self.db.query(Game).filter(
                Game.sport == "NFL",
                Game.game_date >= today,
                Game.game_date <= today + timedelta(days=10),
                Game.game_status.in_(["scheduled", "in_progress"]),
                or_(Game.home_team_id == player.current_team_id, Game.away_team_id == player.current_team_id),
            ).order_by(Game.game_date).first()
            if not game:
                raise ValueError(f"No upcoming NFL game found for {player.name}")
            game_id = game.game_id

        game = self.db.query(Game).filter(Game.game_id == game_id).first()
        season_ids = [game.season_id]
        base = self.dist.calculate_base_distribution(
            player_id=player.player_id,
            stat_type=market_stat,
            sport="NFL",
            season_ids=season_ids,
            min_games=5,
        )
        if not base:
            raise ValueError(f"Insufficient history for {player.name} {market_stat}")

        role = role_for_position(player.position)
        league_mean, league_std = self.pred_service._get_league_averages(
            market_stat, player_position=player.position
        )

        raw = self.calc.calculate_probability_for_line(
            line=float(line),
            player_mean=base["mean"],
            player_std=base["std_dev"],
            sample_size=base["sample_size"],
            stat_type=market_stat,
            league_mean=league_mean,
            league_std=league_std,
            player_role=role,
        )
        model_p = raw["probability"]
        cal_p = raw.get("calibrated_probability", model_p)
        be = american_break_even_odds(cal_p)

        sb_american = None
        implied = None
        edge = None
        if sportsbook_odds:
            sb_american = parse_american_odds(sportsbook_odds)
            implied = american_to_implied(sb_american)
            edge = cal_p - implied

        return PropPriceResult(
            player_name=player.name,
            stat_type=market_stat,
            line=float(line),
            model_probability=model_p,
            calibrated_probability=cal_p,
            break_even_american_odds=be,
            sportsbook_american_odds=sb_american,
            implied_probability=implied,
            edge=edge,
            sample_size=base["sample_size"],
            player_mean=base["mean"],
            player_std=base["std_dev"],
        )
