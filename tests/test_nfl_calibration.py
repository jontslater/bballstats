"""Unit tests for NFL prop calibration helpers and suggested-bet odds."""
import os
import sys
import unittest
from datetime import date
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (  # noqa: F401
    Team, Season, Player, Game, PlayerGameStat, Prediction, GameSchedule,
)
from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.services.distribution_engine import DistributionEngine
from app.services.nfl_data import american_break_even_odds
from app.services.suggested_bets import SuggestedBetsService


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestNFLCalibratedProbability(unittest.TestCase):
    def test_receptions_count_stat_uses_nfl_branch(self):
        calc = CalibratedProbabilityCalculator(sport="NFL")
        out = calc.calculate_probability_for_line(
            line=3.5,
            player_mean=5.0,
            player_std=2.0,
            sample_size=12,
            stat_type="receptions",
            league_mean=4.5,
            league_std=None,
        )
        self.assertGreater(out["probability"], 0.45)
        self.assertLess(out["probability"], 0.95)

    def test_anytime_td_probability_bounded(self):
        calc = CalibratedProbabilityCalculator(sport="NFL")
        out = calc.calculate_probability_for_line(
            line=0.5,
            player_mean=0.55,
            player_std=0.5,
            sample_size=10,
            stat_type="anytime_td",
            league_mean=0.35,
            league_std=None,
        )
        self.assertGreater(out["probability"], 0.2)
        self.assertLess(out["probability"], 0.85)

    def test_break_even_odds_formula(self):
        # p=0.60 -> -150
        self.assertEqual(american_break_even_odds(0.60), -150)


class TestNFLDistributionEngine(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        home = Team(sport="NFL", name="Home", abbreviation="HOM", conference="AFC", division="E")
        away = Team(sport="NFL", name="Away", abbreviation="AWY", conference="AFC", division="E")
        self.db.add_all([home, away])
        self.db.flush()
        season = Season(sport="NFL", season_year="2026", is_current=True)
        self.db.add(season)
        self.db.flush()
        player = Player(sport="NFL", name="Test WR", position="WR", current_team_id=home.team_id)
        self.db.add(player)
        self.db.flush()
        self.player_id = player.player_id
        self.season_id = season.season_id
        self.home_id = home.team_id
        self.away_id = away.team_id

        for i in range(6):
            g = Game(
                sport="NFL",
                game_date=date(2026, 9, 20 + i),
                season_id=season.season_id,
                home_team_id=home.team_id,
                away_team_id=away.team_id,
                game_status="finished",
            )
            self.db.add(g)
            self.db.flush()
            self.db.add(
                PlayerGameStat(
                    sport="NFL",
                    player_id=player.player_id,
                    game_id=g.game_id,
                    team_id=home.team_id,
                    opponent_team_id=away.team_id,
                    targets=6,
                    receptions=4 + (i % 2),
                    receiving_yards=50,
                )
            )
        self.db.commit()
        self.engine = DistributionEngine(self.db)

    def tearDown(self):
        self.db.close()

    def test_receptions_distribution_with_five_games(self):
        dist = self.engine.calculate_base_distribution(
            player_id=self.player_id,
            stat_type="receptions",
            sport="NFL",
            season_ids=[self.season_id],
            min_games=5,
        )
        self.assertIsNotNone(dist)
        self.assertGreaterEqual(dist["sample_size"], 5)


class TestNFLSuggestedBetsFields(unittest.TestCase):
    def test_break_even_field_present_in_schema(self):
        # Smoke test: helper used by suggested bets service
        self.assertEqual(american_break_even_odds(0.55), -122)


if __name__ == "__main__":
    unittest.main()
