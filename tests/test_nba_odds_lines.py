#!/usr/bin/env python3
"""Tests for The Odds API NBA player prop ingestion (mocked HTTP)."""
import os
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import sys

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (  # noqa: F401
    Team,
    Season,
    Player,
    Game,
    Prediction,
    BettingLine,
)
from app.services.nba_odds_lines import (
    MARKET_TO_STAT_TYPE,
    ingest_nba_player_prop_lines,
    match_player_id,
    normalize_player_name,
    normalize_team_name,
)
from app.services.betting_line_service import BettingLineService
from app.services.suggested_bets import SuggestedBetsService
from app.models import NbaPropCalibrationGate


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class MockOddsClient:
    def __init__(self, events: List[Dict], odds_by_event: Dict[str, Dict]):
        self.events = events
        self.odds_by_event = odds_by_event
        self.last_requests_remaining = "499"

    def fetch_nba_events(self, cache_date: str) -> Tuple[List[Dict], bool]:
        return self.events, False

    def fetch_event_odds(
        self,
        event_id: str,
        markets: List[str],
        bookmakers: List[str],
        cache_date: str,
    ) -> Tuple[Optional[Dict], bool]:
        return self.odds_by_event.get(event_id), False


def _seed_game(db):
    home = Team(sport="NBA", abbreviation="LAL", name="Los Angeles Lakers", conference="West", division="P")
    away = Team(sport="NBA", abbreviation="BOS", name="Boston Celtics", conference="East", division="A")
    db.add_all([home, away])
    season = Season(sport="NBA", season_year="2025-26", is_current=True)
    db.add(season)
    db.flush()
    game = Game(
        sport="NBA",
        game_date=date(2025, 11, 1),
        season_id=season.season_id,
        home_team_id=home.team_id,
        away_team_id=away.team_id,
        game_status="scheduled",
        espn_game_id="999",
    )
    player = Player(sport="NBA", player_id=10, name="LeBron James", current_team_id=home.team_id)
    db.add_all([game, player])
    db.flush()
    return game, player, home, away


class TestNameNormalization(unittest.TestCase):
    def test_player_suffix_and_accents(self):
        self.assertEqual(normalize_player_name("Nikola Jokić Jr."), normalize_player_name("nikola jokic"))
        self.assertEqual(normalize_team_name("Los Angeles Clippers"), normalize_team_name("LA Clippers"))

    def test_match_player_on_roster(self):
        db = _session()
        _, player, home, away = _seed_game(db)
        roster = [player, Player(sport="NBA", player_id=11, name="Other Guy", current_team_id=away.team_id)]
        pid = match_player_id("LeBron James", roster)
        self.assertEqual(pid, player.player_id)


class TestOddsIngestion(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.game, self.player, _, _ = _seed_game(self.db)
        self.target = date(2025, 11, 1)
        commence = datetime(2025, 11, 2, 2, 30, tzinfo=timezone.utc)
        self.events = [
            {
                "id": "evt1",
                "sport_key": "basketball_nba",
                "home_team": "Los Angeles Lakers",
                "away_team": "Boston Celtics",
                "commence_time": commence.isoformat().replace("+00:00", "Z"),
            }
        ]
        self.odds = {
            "evt1": {
                "id": "evt1",
                "bookmakers": [
                    {
                        "key": "fanduel",
                        "markets": [
                            {
                                "key": "player_points",
                                "outcomes": [
                                    {
                                        "name": "Over",
                                        "description": "LeBron James",
                                        "price": -115,
                                        "point": 24.5,
                                    },
                                    {
                                        "name": "Under",
                                        "description": "LeBron James",
                                        "price": -105,
                                        "point": 24.5,
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        }

    def tearDown(self):
        self.db.close()

    def test_ingest_writes_betting_line(self):
        client = MockOddsClient(self.events, self.odds)
        summary = ingest_nba_player_prop_lines(self.db, client, self.target)
        self.assertEqual(summary.events_considered, 1)
        self.assertEqual(summary.lines_upserted, 1)
        line = (
            self.db.query(BettingLine)
            .filter(
                BettingLine.game_id == self.game.game_id,
                BettingLine.player_id == self.player.player_id,
                BettingLine.stat_type == "points",
            )
            .one()
        )
        self.assertEqual(line.over_line, 24.5)
        self.assertEqual(line.over_odds, "-115")
        self.assertEqual(line.sportsbook, "FanDuel")
        self.assertEqual(line.source, "api")

    def test_draftkings_fallback(self):
        odds = {
            "evt1": {
                "id": "evt1",
                "bookmakers": [
                    {"key": "fanduel", "markets": [{"key": "player_points", "outcomes": []}]},
                    {
                        "key": "draftkings",
                        "markets": [
                            {
                                "key": "player_points",
                                "outcomes": [
                                    {
                                        "name": "Over",
                                        "description": "LeBron James",
                                        "price": 120,
                                        "point": 25.5,
                                    },
                                    {
                                        "name": "Under",
                                        "description": "LeBron James",
                                        "price": -140,
                                        "point": 25.5,
                                    },
                                ],
                            }
                        ],
                    },
                ],
            }
        }
        client = MockOddsClient(self.events, odds)
        ingest_nba_player_prop_lines(self.db, client, self.target)
        line = self.db.query(BettingLine).one()
        self.assertEqual(line.sportsbook, "DraftKings")
        self.assertEqual(line.over_odds, "+120")

    def test_predictions_only_skips_other_games(self):
        client = MockOddsClient(self.events, self.odds)
        summary = ingest_nba_player_prop_lines(
            self.db, client, self.target, predictions_only=True
        )
        self.assertEqual(summary.lines_upserted, 0)
        self.assertEqual(summary.skipped_predictions_filter, 1)

    def test_suggested_bets_use_ingested_line(self):
        self.db.add(NbaPropCalibrationGate(stat_type="points", passes_gate=True, prob_adjustment=0.0))
        self.db.add(
            Prediction(
                sport="NBA",
                player_id=self.player.player_id,
                game_id=self.game.game_id,
                stat_type="points",
                bet_type="safe",
                safe_line=24.5,
                safe_probability=0.62,
                standard_line=26.5,
                standard_probability=0.55,
                confidence_level="HIGH",
            )
        )
        self.db.commit()
        client = MockOddsClient(self.events, self.odds)
        ingest_nba_player_prop_lines(self.db, client, self.target)
        svc = SuggestedBetsService(self.db, sport="NBA")
        bets = svc.get_suggested_bets(game_date=self.target, limit=5)
        self.assertGreaterEqual(len(bets), 1)


class TestOddsApiClientCache(unittest.TestCase):
    def test_cache_roundtrip(self):
        from app.scrapers.odds_api_client import OddsApiClient
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            client = OddsApiClient("test-key", cache_dir=Path(tmp), use_cache=True)
            path = client._cache_path("2025-11-01", "events.json")
            client._write_cache(path, [{"id": "evt1"}])
            data = client._read_cache(path)
            self.assertEqual(data[0]["id"], "evt1")


if __name__ == "__main__":
    unittest.main()
