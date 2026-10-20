#!/usr/bin/env python3
"""No-network ESPN parsing and idempotent game dedupe tests."""
import json
import os
import unittest
from datetime import date
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

backend_path = Path(__file__).parent.parent / "backend"
sys_path = str(backend_path)
import sys

sys.path.insert(0, sys_path)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (  # noqa: F401
    Team,
    Season,
    Player,
    Game,
    PlayerGameStat,
    GameSchedule,
    Injury,
    Lineup,
    Prediction,
    BettingLine,
)
from app.scrapers.espn_nba_client import ESPNNBAClient, parse_minutes_value
from app.services.nba_results import upsert_final_from_espn
from app.services.nba_schedule import persist_nba_schedule_games


FIXTURE = Path(__file__).parent / "fixtures" / "espn_nba_summary_min.json"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_nba(db):
    teams = [
        ("OKC", "Oklahoma City Thunder"),
        ("HOU", "Houston Rockets"),
    ]
    by = {}
    for abbr, name in teams:
        t = Team(sport="NBA", abbreviation=abbr, name=name, conference="West", division="NW")
        db.add(t)
        db.flush()
        by[abbr] = t
    season = Season(sport="NBA", season_year="2025-26", start_date=date(2025, 10, 21), end_date=date(2026, 4, 12), is_current=True)
    db.add(season)
    db.flush()
    return by, season


class TestESPNParsing(unittest.TestCase):
    def test_parse_minutes(self):
        self.assertEqual(parse_minutes_value("47"), 47)
        self.assertEqual(parse_minutes_value("24:30"), 25)

    def test_parse_box_score_fixture(self):
        data = json.loads(FIXTURE.read_text())
        client = ESPNNBAClient()
        parsed = client.parse_box_score(data, game_meta={"home_team": "OKC", "away_team": "HOU"})
        self.assertIsNotNone(parsed)
        self.assertGreaterEqual(len(parsed["player_stats"]), 10)
        starters = [p for p in parsed["player_stats"] if p.get("is_starter")]
        self.assertGreaterEqual(len(starters), 4)
        kd = next(p for p in parsed["player_stats"] if "Durant" in p["player_name"])
        self.assertEqual(kd["points"], 23)
        self.assertEqual(kd["minutes_played"], 47)


class TestNbaDedupe(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.teams, self.season = _seed_nba(self.db)

    def tearDown(self):
        self.db.close()

    def test_persist_schedule_idempotent_by_espn_game_id(self):
        game = {
            "espn_game_id": "401809243",
            "game_date": date(2025, 10, 21),
            "home_team": "OKC",
            "away_team": "HOU",
            "status": "scheduled",
        }
        r1 = persist_nba_schedule_games(self.db, [game], self.season)
        r2 = persist_nba_schedule_games(self.db, [game], self.season)
        self.db.commit()
        self.assertEqual(r1["created_games"], 1)
        self.assertEqual(r2["created_games"], 0)
        count = self.db.query(Game).filter(Game.espn_game_id == "401809243").count()
        self.assertEqual(count, 1)

    def test_box_score_upsert_no_duplicate_stats(self):
        data = json.loads(FIXTURE.read_text())
        client = ESPNNBAClient()
        api_game = {
            "espn_game_id": "401809243",
            "game_date": date(2025, 10, 21),
            "home_team": "OKC",
            "away_team": "HOU",
            "status": "finished",
            "home_score": 125,
            "away_score": 124,
        }

        class StubClient:
            def get_box_score_for_game(self, _gid, game_meta=None):
                return client.parse_box_score(data, game_meta=game_meta)

        g1, created1, n1 = upsert_final_from_espn(self.db, StubClient(), api_game, self.season)
        self.db.commit()
        g2, created2, n2 = upsert_final_from_espn(self.db, StubClient(), api_game, self.season, skip_if_complete=True)
        self.db.commit()
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertGreater(n1, 0)
        self.assertEqual(n2, 0)
        stats = self.db.query(PlayerGameStat).filter(PlayerGameStat.game_id == g1.game_id).count()
        self.assertEqual(stats, n1)


if __name__ == "__main__":
    unittest.main()
