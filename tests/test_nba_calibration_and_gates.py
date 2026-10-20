#!/usr/bin/env python3
"""Tests for NBA player id allocation, calibration math, gates, and suggested-bet rules."""
import os
import unittest
from datetime import date
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import sys

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (  # noqa: F401
    Team,
    Season,
    Player,
    Game,
    PlayerGameStat,
    GameSchedule,
    Prediction,
    BettingLine,
    NbaPropCalibrationGate,
)
from app.services.nba_prop_calibration import (
    _median_line_p_over_all,
    prop_passes_calibration_gate,
    refresh_prop_gate_cache,
)
from app.services.nba_results import get_or_create_nba_player
from app.services.betting_line_service import BettingLineService
from app.services.suggested_bets import SuggestedBetsService


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestNbaPlayerIdAllocation(unittest.TestCase):
    def test_uses_global_max_player_id(self):
        db = _session()
        mlb = Player(sport="MLB", player_id=500, name="Pitcher")
        db.add(mlb)
        db.flush()
        team = Team(sport="NBA", abbreviation="OKC", name="Thunder", conference="West", division="NW")
        db.add(team)
        db.flush()
        nba_player = get_or_create_nba_player(db, "Test Player", team, espn_player_id="999")
        db.commit()
        self.assertEqual(nba_player.player_id, 501)


class TestMedianLinePOver(unittest.TestCase):
    def test_median_over_all_predictions_not_only_mid_band(self):
        preds = [(0.52, 1, 10.5), (0.62, 0, 12.5), (0.48, 1, 8.5)]
        self.assertAlmostEqual(_median_line_p_over_all(preds), (0.52 + 0.62 + 0.48) / 3, places=5)


class TestCalibrationGates(unittest.TestCase):
    def test_gate_defaults_false_without_db_rows(self):
        self.assertFalse(prop_passes_calibration_gate("points"))

    def test_persisted_gate_loaded(self):
        db = _session()
        db.add(NbaPropCalibrationGate(stat_type="points", passes_gate=True, prob_adjustment=0.02))
        db.commit()
        from app.services.nba_prop_calibration import load_prop_gates

        load_prop_gates(db, max_age_hours=9999)
        self.assertTrue(prop_passes_calibration_gate("points", db=db))


class TestBettingLineMatch(unittest.TestCase):
    def test_find_line_requires_stat_and_close_line(self):
        db = _session()
        team = Team(sport="NBA", abbreviation="BOS", name="Celtics", conference="East", division="A")
        db.add(team)
        season = Season(sport="NBA", season_year="2026-27", is_current=True)
        db.add(season)
        db.flush()
        game = Game(
            sport="NBA",
            game_date=date.today(),
            season_id=season.season_id,
            home_team_id=team.team_id,
            away_team_id=team.team_id,
            espn_game_id="999",
        )
        player = Player(sport="NBA", player_id=1, name="Star", current_team_id=team.team_id)
        db.add_all([game, player])
        db.flush()
        db.add(
            BettingLine(
                game_id=game.game_id,
                player_id=player.player_id,
                stat_type="points",
                over_line=24.5,
                over_odds="-110",
                sportsbook="DraftKings",
            )
        )
        db.commit()
        svc = BettingLineService(db)
        self.assertIsNotNone(svc.find_matching_line(game.game_id, player.player_id, "points", 24.5))
        self.assertIsNone(svc.find_matching_line(game.game_id, player.player_id, "points", 30.0))


class TestSuggestedBetsRequireSportsbookLine(unittest.TestCase):
    def test_no_line_means_no_suggestion(self):
        db = _session()
        home = Team(sport="NBA", abbreviation="LAL", name="Lakers", conference="West", division="P")
        away = Team(sport="NBA", abbreviation="BOS", name="Celtics", conference="East", division="A")
        db.add_all([home, away])
        season = Season(sport="NBA", season_year="2026-27", is_current=True)
        db.add(season)
        db.flush()
        game = Game(
            sport="NBA",
            game_date=date.today(),
            season_id=season.season_id,
            home_team_id=home.team_id,
            away_team_id=away.team_id,
            game_status="scheduled",
            espn_game_id="888",
        )
        player = Player(sport="NBA", player_id=2, name="Star", current_team_id=home.team_id)
        db.add_all([game, player])
        db.flush()
        db.add(
            NbaPropCalibrationGate(stat_type="points", passes_gate=True, prob_adjustment=0.0)
        )
        db.add(
            Prediction(
                sport="NBA",
                player_id=player.player_id,
                game_id=game.game_id,
                stat_type="points",
                bet_type="safe",
                safe_line=22.5,
                safe_probability=0.62,
                standard_line=24.5,
                standard_probability=0.58,
                confidence_level="HIGH",
                line_source="sportsbook",
            )
        )
        db.commit()
        from app.services.nba_prop_calibration import load_prop_gates

        load_prop_gates(db, max_age_hours=9999)
        bets = SuggestedBetsService(db, sport="NBA").get_suggested_bets(game_date=date.today(), limit=10)
        self.assertEqual(bets, [])


if __name__ == "__main__":
    unittest.main()
