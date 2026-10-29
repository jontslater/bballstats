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
    fit_shrunk_tier_subtract,
)
from app.services.nba_prop_backtest import sample_candidates
from app.services.nba_prop_player_cache import PlayerStatHistoryCache, PitCandidate
from app.services.nba_prop_prob_fit import fit_prob_shrink_brier
from app.services.nba_season_blend import nba_rate_scaled_mean
from app.services.nba_sportsbook_edge import shrink_probability


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestMeanBiasCorrection(unittest.TestCase):
    def test_no_op_without_offsets(self):
        self.assertAlmostEqual(apply_mean_bias_correction(30.0, "points"), 30.0)

    def test_subtracts_when_offsets_provided(self):
        corrected = apply_mean_bias_correction(
            30.0, "points", offsets={"star": 2.0}
        )
        self.assertAlmostEqual(corrected, 28.0)

    def test_fit_shrunk_caps(self):
        errors = [("points", "star", 5.0)] * 10
        off = fit_shrunk_tier_subtract(errors, per_tier_cap=2.0, shrink_prior_n=5.0)
        self.assertLessEqual(off["star"], 2.0)


class TestProbShrink(unittest.TestCase):
    def test_shrink_moves_toward_half(self):
        self.assertLess(shrink_probability(0.7, 0.5), 0.7)

    def test_fit_reduces_overconfidence(self):
        samples = [(0.65, False)] * 40 + [(0.65, True)] * 10
        s = fit_prob_shrink_brier(samples)
        self.assertLess(s, 1.0)


class TestRateScaledMeanCap(unittest.TestCase):
    def test_caps_high_projected_minutes(self):
        uncapped = nba_rate_scaled_mean(20.0, 30.0, 36.0, max_minutes_ratio=1.05)
        self.assertAlmostEqual(uncapped, 20.0 * 31.5 / 30.0, places=2)


class TestPlayerCache(unittest.TestCase):
    def test_rolling_median_prior_only(self):
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
        cache = PlayerStatHistoryCache(db, [season.season_id])
        med = cache.rolling_median(player.player_id, "points", date(2025, 11, 6))
        self.assertEqual(med, 14.0)
        db.close()


class TestPitSampling(unittest.TestCase):
    def test_stride_sample_spreads(self):
        cands = [
            PitCandidate(1, 1, "points", date(2025, 10, i), float(i)) for i in range(1, 11)
        ]
        picked = sample_candidates(cands, 5, strategy="stride")
        self.assertEqual(len(picked), 5)


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
