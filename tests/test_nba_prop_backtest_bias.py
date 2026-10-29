#!/usr/bin/env python3
"""Tests for NBA PIT backtest helpers and mean bias correction."""
import os
import unittest
from datetime import date
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import sys

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Game, Player, PlayerGameStat, Season, Team
from app.services.distribution_engine import DistributionEngine
from app.services.nba_mean_bias_correction import (
    apply_mean_bias_correction,
    bias_report_from_errors,
)
from app.services.nba_prop_backtest import rolling_median_proxy_line
from app.services.nba_season_blend import nba_rate_scaled_mean


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestMeanBiasCorrection(unittest.TestCase):
    def test_subtracts_star_tier_for_points(self):
        corrected = apply_mean_bias_correction(30.0, "points")
        self.assertLess(corrected, 30.0)
        self.assertAlmostEqual(corrected, 30.0 - 6.02, places=2)

    def test_bias_report(self):
        errors = [("points", "star", 6.0), ("points", "bench", 1.0)]
        rep = bias_report_from_errors(errors)
        self.assertEqual(rep["n"], 2)
        self.assertAlmostEqual(rep["overall_mean_bias"], 3.5, places=2)


class TestRateScaledMeanCap(unittest.TestCase):
    def test_caps_high_projected_minutes(self):
        uncapped = nba_rate_scaled_mean(20.0, 30.0, 36.0, max_minutes_ratio=1.05)
        self.assertAlmostEqual(uncapped, 20.0 * 31.5 / 30.0, places=2)


class TestRollingMedian(unittest.TestCase):
    def test_uses_only_prior_games(self):
        db = _session()
        team = Team(sport="NBA", abbreviation="BOS", name="Celtics", conference="E", division="A")
        season = Season(sport="NBA", season_year="2025-26", is_current=True)
        player = Player(sport="NBA", name="P", current_team_id=1)
        db.add_all([team, season, player])
        db.flush()
        player.current_team_id = team.team_id
        db.flush()
        for i, pts in enumerate([10, 12, 14, 16, 18]):
            g = Game(
                sport="NBA",
                game_date=date(2025, 11, 1 + i),
                season_id=season.season_id,
                home_team_id=team.team_id,
                away_team_id=team.team_id,
                game_status="finished",
            )
            db.add(g)
            db.flush()
            db.add(
                PlayerGameStat(
                    sport="NBA",
                    player_id=player.player_id,
                    game_id=g.game_id,
                    team_id=team.team_id,
                    opponent_team_id=team.team_id,
                    minutes_played=30,
                    points=pts,
                )
            )
        db.commit()
        med = rolling_median_proxy_line(
            db, player.player_id, "points", date(2025, 11, 6), season_ids=[season.season_id]
        )
        self.assertEqual(med, 14.0)
        db.close()


class TestDistributionAsOf(unittest.TestCase):
    def test_excludes_games_on_or_after_as_of(self):
        db = _session()
        team = Team(sport="NBA", abbreviation="BOS", name="Celtics", conference="E", division="A")
        season = Season(sport="NBA", season_year="2025-26", is_current=True)
        player = Player(sport="NBA", name="P", current_team_id=1)
        db.add_all([team, season, player])
        db.flush()
        player.current_team_id = team.team_id
        db.flush()
        for i, pts in enumerate([10] * 14 + [40] * 5):
            g = Game(
                sport="NBA",
                game_date=date(2025, 10, 1 + i),
                season_id=season.season_id,
                home_team_id=team.team_id,
                away_team_id=team.team_id,
                game_status="finished",
            )
            db.add(g)
            db.flush()
            db.add(
                PlayerGameStat(
                    sport="NBA",
                    player_id=player.player_id,
                    game_id=g.game_id,
                    team_id=team.team_id,
                    opponent_team_id=team.team_id,
                    minutes_played=30,
                    points=pts,
                )
            )
        db.commit()
        engine = DistributionEngine(db)
        dist = engine.calculate_base_distribution(
            player.player_id,
            "points",
            sport="NBA",
            projected_minutes=28.0,
            season_ids=[season.season_id],
            min_games=10,
            as_of_date=date(2025, 10, 15),
        )
        self.assertIsNotNone(dist)
        self.assertLess(dist["mean"], 15.0)
        db.close()


if __name__ == "__main__":
    unittest.main()
