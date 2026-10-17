"""
Price a single NFL player prop against a sportsbook line (e.g. FanDuel via The Odds API).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models import Game, Player
from app.services.nfl_data import american_break_even_odds
from app.services.nfl_prop_inference import compute_nfl_line_probabilities

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

        probs = compute_nfl_line_probabilities(
            self.db,
            player_id=player.player_id,
            game_id=game_id,
            stat_type=market_stat,
            line=float(line),
            apply_posthoc=True,
        )
        if not probs:
            raise ValueError(f"Insufficient history for {player.name} {market_stat}")

        model_p = probs["model_probability"]
        cal_p = probs["calibrated_probability"]
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
            sample_size=probs["sample_size"],
            player_mean=probs["player_mean"],
            player_std=probs["player_std"],
        )
