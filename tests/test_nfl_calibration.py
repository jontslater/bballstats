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


class TestNFLHistoryHelper(unittest.TestCase):
    def test_unknown_stat_returns_dict_not_list(self):
        from app.services.prediction_history_helper import get_last_n_games_for_stat

        db = _session()
        try:
            out = get_last_n_games_for_stat(db, player_id=1, stat_type="rushing_attempts", sport="NFL")
            self.assertIsInstance(out, dict)
            self.assertIn("games", out)
        finally:
            db.close()


class TestNFLBetLineFloors(unittest.TestCase):
    def test_passing_yards_standard_not_half(self):
        from app.services.bet_definitions import BetDefinitions

        defs = BetDefinitions(sport="NFL")
        lines = defs.calculate_bet_lines(
            adjusted_mean=245,
            adjusted_std=45,
            sample_size=12,
            stat_type="passing_yards",
            median_line=238,
            player_role="QB",
            league_mean=220,
        )
        self.assertGreaterEqual(lines["standard_line"], 149.5)
        self.assertGreater(lines["safe_line"], 50)


class TestNFLDataLoader(unittest.TestCase):
    def test_modern_stats_include_2025(self):
        from app.services.nfl_data import load_nflverse_player_stats

        df = load_nflverse_player_stats([2025])
        self.assertFalse(df.empty)
        self.assertIn("recent_team", df.columns)
        self.assertTrue((df["season"] == 2025).any())


class TestNFLMedianSymmetry(unittest.TestCase):
    def test_yards_near_median_fifty_fifty(self):
        calc = CalibratedProbabilityCalculator(sport="NFL")
        mean = 248.0
        median = 235.0
        line = round(median * 2) / 2 - 0.5
        out = calc.calculate_probability_for_line(
            line=line,
            player_mean=mean,
            player_std=42.0,
            sample_size=14,
            stat_type="passing_yards",
            league_mean=220.0,
            player_role="QB",
            player_median=median,
            apply_posthoc=False,
        )
        self.assertGreater(out["probability"], 0.42)
        self.assertLess(out["probability"], 0.58)

    def test_backtest_median_line_fairness(self):
        import importlib.util

        path = Path(__file__).parent.parent / "scripts" / "backtest_nfl_calibration.py"
        spec = importlib.util.spec_from_file_location("backtest_nfl_calibration", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        averages = mod.compute_median_p_over([2024], max_week=18, min_history=5)
        mod.assert_median_fairness(averages, low=0.45, high=0.55)


class TestNFLTailAndSymmetry(unittest.TestCase):
    def test_high_completion_line_low_probability(self):
        calc = CalibratedProbabilityCalculator(sport="NFL")
        out = calc.calculate_probability_for_line(
            line=31.5,
            player_mean=24.9,
            player_std=4.0,
            sample_size=12,
            stat_type="completions",
            league_mean=21.0,
            player_role="QB",
            apply_posthoc=False,
        )
        self.assertLess(out["probability"], 0.12)

    def test_symmetric_posthoc_preserves_complement(self):
        from app.services.nfl_posthoc_calibration import NFLPosthocCalibrator

        cal = NFLPosthocCalibrator(params_path=backend_path / "data" / "nfl_isotonic_calibration.json")
        p = 0.62
        q = 1.0 - p
        for stat in ("completions", "receptions", "rushing_yards"):
            cp = cal.apply(stat, p)
            cq = cal.apply(stat, q)
            self.assertAlmostEqual(cp + cq, 1.0, delta=0.02)


class TestNFLPosthocFitter(unittest.TestCase):
    def test_fit_disables_when_no_improvement(self):
        from app.services.nfl_posthoc_calibration import NFLPosthocCalibrator

        pairs = [(0.55, 1), (0.45, 0)] * 120
        res = NFLPosthocCalibrator.fit_symmetric_alpha_holdout(pairs, min_samples=100)
        self.assertIsNotNone(res)
        self.assertFalse(res.get("enabled", True))


class TestAnytimeTDDefinition(unittest.TestCase):
    def test_distribution_anytime_excludes_passing(self):
        from app.services.distribution_engine import DistributionEngine

        db = _session()
        try:
            home = Team(sport="NFL", name="H", abbreviation="HH", conference="AFC", division="E")
            away = Team(sport="NFL", name="A", abbreviation="AA", conference="AFC", division="E")
            db.add_all([home, away])
            db.flush()
            season = Season(sport="NFL", season_year="2026", is_current=True)
            db.add(season)
            db.flush()
            qb = Player(sport="NFL", name="QB", position="QB", current_team_id=home.team_id)
            db.add(qb)
            db.flush()
            for i in range(6):
                g = Game(
                    sport="NFL",
                    game_date=date(2026, 9, 10 + i),
                    season_id=season.season_id,
                    home_team_id=home.team_id,
                    away_team_id=away.team_id,
                    game_status="finished",
                )
                db.add(g)
                db.flush()
                db.add(
                    PlayerGameStat(
                        sport="NFL",
                        player_id=qb.player_id,
                        game_id=g.game_id,
                        team_id=home.team_id,
                        opponent_team_id=away.team_id,
                        pass_attempts=30,
                        passing_tds=3,
                        rushing_tds=0,
                        receiving_tds=0,
                    )
                )
            db.commit()
            dist = DistributionEngine(db).calculate_base_distribution(
                qb.player_id, "anytime_td", sport="NFL", season_ids=[season.season_id], min_games=5
            )
            self.assertIsNotNone(dist)
            self.assertEqual(dist["mean"], 0.0)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
