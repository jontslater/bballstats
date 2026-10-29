#!/usr/bin/env python3
"""Tests for NBA season blending, pipeline checks, sportsbook gaps, and API redaction."""
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
from app.models import Team, Season, Player, Game, PlayerGameStat
from app.scrapers.odds_api_client import OddsApiClient, OddsApiError, _redact_api_key
from app.services.distribution_engine import DistributionEngine
from app.services.nba_pipeline_helpers import nba_prediction_generation_ok
from app.services.nba_season_blend import (
    blended_nba_avg_minutes,
    blended_nba_base_distribution,
    nba_rate_scaled_mean,
    _blend_stats,
)
from app.services.nba_sportsbook_edge import (
    mean_book_gap_limit,
    mean_vs_book_misaligned,
    stat_point_edge_exceeds_cap,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestSeasonBlend(unittest.TestCase):
    def test_blend_weights_current_as_games_accrue(self):
        current = {"mean": 20.0, "std_dev": 5.0, "sample_size": 5}
        prior = {"mean": 30.0, "std_dev": 6.0, "sample_size": 40}
        out = _blend_stats(current, prior, n_current=5, min_current=10)
        self.assertAlmostEqual(out["blend_weight_current"], 0.5, places=3)
        self.assertAlmostEqual(out["mean"], 25.0, places=2)

    def test_rate_scaled_mean_lowers_for_fewer_minutes(self):
        scaled = nba_rate_scaled_mean(20.0, 32.0, 24.0)
        self.assertAlmostEqual(scaled, 15.0, places=2)

    def test_blended_distribution_uses_prior_when_no_current_games(self):
        db = _session()
        team = Team(sport="NBA", abbreviation="BOS", name="Celtics", conference="E", division="A")
        prev = Season(
            sport="NBA",
            season_year="2025-26",
            is_current=False,
            start_date=date(2025, 10, 1),
            end_date=date(2026, 6, 30),
        )
        cur = Season(
            sport="NBA",
            season_year="2026-27",
            is_current=True,
            start_date=date(2026, 10, 1),
            end_date=date(2027, 6, 30),
        )
        player = Player(sport="NBA", player_id=1, name="Star", current_team_id=1)
        db.add(team)
        db.add_all([prev, cur])
        db.flush()
        player.current_team_id = team.team_id
        db.add(player)
        db.flush()
        for i in range(12):
            g = Game(
                sport="NBA",
                game_date=date(2026, 1, 1),
                season_id=prev.season_id,
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
                    points=18,
                    rebounds=5,
                    assists=4,
                )
            )
        db.commit()
        engine = DistributionEngine(db)
        dist = blended_nba_base_distribution(
            engine, db, player.player_id, "points", 28.0, cur.season_id, min_games=10
        )
        self.assertIsNotNone(dist)
        self.assertGreater(dist["mean"], 0)
        mins = blended_nba_avg_minutes(engine, db, player.player_id, cur.season_id)
        self.assertIsNotNone(mins)
        db.close()


class TestSportsbookGapScaling(unittest.TestCase):
    def test_stat_scaled_gap(self):
        self.assertFalse(mean_vs_book_misaligned(24.0, 22.0, "points"))
        self.assertTrue(mean_vs_book_misaligned(30.0, 22.0, "points"))

    def test_point_edge_cap(self):
        self.assertTrue(stat_point_edge_exceeds_cap(35.0, 20.0))
        self.assertFalse(stat_point_edge_exceeds_cap(24.0, 20.0))
        self.assertEqual(mean_book_gap_limit("rebounds"), 2.5)


class TestOddsRedaction(unittest.TestCase):
    def test_request_exception_redacts_key(self):
        msg = _redact_api_key(
            "HTTPSConnectionPool host=api.the-odds-api.com/?apiKey=secret123",
            "secret123",
        )
        self.assertNotIn("secret123", msg)
        self.assertIn("REDACTED", msg)


class TestPipelinePredictionCheck(unittest.TestCase):
    def test_fails_when_games_exist_without_predictions(self):
        db = _session()
        team = Team(sport="NBA", abbreviation="LAL", name="Lakers", conference="W", division="P")
        season = Season(sport="NBA", season_year="2026-27", is_current=True)
        db.add_all([team, season])
        db.flush()
        game = Game(
            sport="NBA",
            game_date=date.today(),
            season_id=season.season_id,
            home_team_id=team.team_id,
            away_team_id=team.team_id,
            game_status="scheduled",
        )
        db.add(game)
        db.commit()
        ok, _ = nba_prediction_generation_ok(db, days_ahead=0, created=0, updated=0)
        self.assertFalse(ok)
        db.close()


if __name__ == "__main__":
    unittest.main()
