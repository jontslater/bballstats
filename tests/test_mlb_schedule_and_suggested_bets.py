#!/usr/bin/env python3
"""
Tests for MLB postseason schedule persistence and suggested-bets date scoping.

Covers:
  (a) postseason schedule inclusion (gameType F/D/L/W) without duplicating games
  (b) empty-date returns empty suggestions
  (c) finished series games are not suggested for a later date
"""
import os
import sys
import unittest
from datetime import date
from pathlib import Path

# app.database creates an engine on import; keep unit tests off Postgres.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (  # noqa: F401 — register all tables
    Team, Season, Player, Game, PlayerGameStat, Injury, TeamPositionDefense,
    PlayerTeamMatchup, InjuryImpactHistory, Prediction, GameSchedule, UserPlay,
    Lineup, BettingLine, Parlay, PoorMansBetChallenge, PoorMansBetDay,
    ValueLadder, HistoricalSuggestedBet, HistoricalParlay, HistoricalParlayLeg,
)
from app.services.mlb_schedule import (
    MLB_INCLUDED_GAME_TYPES,
    mlb_external_game_id,
    persist_mlb_schedule_games,
)
from app.services.suggested_bets import SuggestedBetsService, SUGGESTABLE_GAME_STATUSES


def _session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_mlb(db):
    teams = [
        ('CWS', 'Chicago White Sox', 145),
        ('CLE', 'Cleveland Guardians', 114),
        ('NYY', 'New York Yankees', 147),
        ('TBR', 'Tampa Bay Rays', 139),
        ('BOS', 'Boston Red Sox', 111),
        ('CHC', 'Chicago Cubs', 112),
        ('SDP', 'San Diego Padres', 135),
    ]
    by_abbrev = {}
    for abbr, name, _mlb_id in teams:
        t = Team(sport='MLB', name=name, abbreviation=abbr, conference='AL', division='East')
        db.add(t)
        db.flush()
        by_abbrev[abbr] = t
    season = Season(sport='MLB', season_year='2026', is_current=True)
    db.add(season)
    db.flush()
    return by_abbrev, season


def _api_game(game_pk, game_date, game_type, status, away_id, home_id):
    return {
        'game_id': game_pk,
        'game_date': game_date,
        'game_type': game_type,
        'status': status,
        'away_id': away_id,
        'home_id': home_id,
    }


class TestMlbPostseasonSchedule(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.teams, self.season = _seed_mlb(self.db)

    def tearDown(self):
        self.db.close()

    def test_included_types_cover_postseason_series(self):
        self.assertTrue({'R', 'F', 'D', 'L', 'W', 'P'} <= MLB_INCLUDED_GAME_TYPES)
        self.assertEqual(mlb_external_game_id(849834), 'MLB_849834')

    def test_postseason_games_are_persisted_as_games_and_schedules(self):
        """(a) ALDS/NLDS-style gameType=D/F rows become Game + GameSchedule."""
        api_games = [
            _api_game(849834, '2026-10-05', 'D', 'Pre-Game', 145, 114),  # CWS @ CLE
            _api_game(849839, '2026-10-05', 'D', 'Scheduled', 147, 139),  # NYY @ TBR
            _api_game(849850, '2026-10-06', 'F', 'Scheduled', 112, 135),  # CHC @ SDP wild card
        ]
        result = persist_mlb_schedule_games(self.db, api_games, self.season)
        self.db.commit()

        self.assertEqual(result['created_games'], 3)
        self.assertEqual(result['created_schedules'], 3)
        self.assertEqual(result['errors'], 0)

        games = self.db.query(Game).filter(Game.sport == 'MLB').order_by(Game.espn_game_id).all()
        self.assertEqual(len(games), 3)
        ids = {g.espn_game_id for g in games}
        self.assertEqual(ids, {'MLB_849834', 'MLB_849839', 'MLB_849850'})
        for g in games:
            self.assertEqual(g.game_status, 'scheduled')
            self.assertIn(g.game_date, (date(2026, 10, 5), date(2026, 10, 6)))

        schedules = self.db.query(GameSchedule).filter(GameSchedule.sport == 'MLB').all()
        self.assertEqual(len(schedules), 3)
        for s in schedules:
            self.assertEqual(s.external_game_id, s.nba_game_id)
            self.assertTrue(s.external_game_id.startswith('MLB_'))
            self.assertIsNotNone(s.game_id)

        oct5 = [g for g in games if g.game_date == date(2026, 10, 5)]
        self.assertEqual(len(oct5), 2)

    def test_persist_does_not_duplicate_existing_gamepk(self):
        api_games = [
            _api_game(849834, '2026-10-05', 'D', 'Scheduled', 145, 114),
        ]
        persist_mlb_schedule_games(self.db, api_games, self.season)
        self.db.commit()
        result = persist_mlb_schedule_games(self.db, api_games, self.season)
        self.db.commit()

        self.assertEqual(result['created_games'], 0)
        self.assertEqual(result['updated_games'], 1)
        self.assertEqual(self.db.query(Game).filter(Game.sport == 'MLB').count(), 1)
        self.assertEqual(self.db.query(GameSchedule).filter(GameSchedule.sport == 'MLB').count(), 1)

        game = self.db.query(Game).one()
        self.assertEqual(game.espn_game_id, 'MLB_849834')

    def test_all_star_game_type_is_skipped(self):
        api_games = [
            _api_game(1, '2026-07-14', 'A', 'Scheduled', 145, 114),
            _api_game(849834, '2026-10-05', 'D', 'Scheduled', 145, 114),
        ]
        result = persist_mlb_schedule_games(self.db, api_games, self.season)
        self.db.commit()
        self.assertEqual(result['skipped_type'], 1)
        self.assertEqual(result['created_games'], 1)
        self.assertEqual(self.db.query(Game).count(), 1)
        self.assertEqual(self.db.query(Game).one().espn_game_id, 'MLB_849834')

    def test_regular_season_still_persisted(self):
        api_games = [
            _api_game(700001, '2026-09-20', 'R', 'Final', 111, 147),  # BOS @ NYY
        ]
        persist_mlb_schedule_games(self.db, api_games, self.season)
        self.db.commit()
        game = self.db.query(Game).one()
        self.assertEqual(game.game_status, 'finished')
        self.assertEqual(game.espn_game_id, 'MLB_700001')


class TestSuggestedBetsDateScoping(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.teams, self.season = _seed_mlb(self.db)
        self.service = SuggestedBetsService(self.db, sport='MLB')

    def tearDown(self):
        self.db.close()

    def _game(self, game_date, home_abbr, away_abbr, status, espn_id=None):
        g = Game(
            sport='MLB',
            game_date=game_date,
            season_id=self.season.season_id,
            home_team_id=self.teams[home_abbr].team_id,
            away_team_id=self.teams[away_abbr].team_id,
            game_status=status,
            espn_game_id=espn_id,
        )
        self.db.add(g)
        self.db.flush()
        return g

    def test_empty_date_returns_empty_suggestions(self):
        """(b) A date with zero qualifying games returns [] (caller should SKIP)."""
        self._game(date(2026, 10, 1), 'NYY', 'BOS', 'finished', 'MLB_old')
        self.db.commit()

        self.assertEqual(self.service.get_suggested_bets(game_date=date(2026, 10, 5)), [])
        self.assertEqual(self.service._games_for_suggestions(date(2026, 10, 5)), [])

    def test_finished_series_not_suggested_for_later_date(self):
        """(c) Finished Wild Card / DS games must not appear as a later date's picks."""
        finished = self._game(date(2026, 10, 1), 'NYY', 'BOS', 'finished', 'MLB_bos_nyy')
        also_finished = self._game(date(2026, 9, 29), 'SDP', 'CHC', 'finished', 'MLB_chc_sdp')
        player = Player(sport='MLB', name='Garrett Crochet', position='P',
                        current_team_id=self.teams['BOS'].team_id)
        self.db.add(player)
        self.db.flush()
        self.db.add(Prediction(
            sport='MLB',
            player_id=player.player_id,
            game_id=finished.game_id,
            stat_type='strikeouts',
            bet_type='safe',
            safe_line=0.5,
            safe_probability=0.92,
            confidence_level='HIGH',
        ))
        self.db.commit()

        later = date(2026, 10, 5)
        self.assertEqual(self.service.get_suggested_bets(game_date=later), [])
        self.assertEqual(self.service._games_for_suggestions(later), [])
        # Even asking for the finished date must not surface finished games as bets
        self.assertEqual(self.service._games_for_suggestions(date(2026, 10, 1)), [])
        self.assertEqual(self.service.get_suggested_bets(game_date=date(2026, 10, 1)), [])
        self.assertNotIn(also_finished.game_id, [g.game_id for g in self.service._games_for_suggestions(later)])

    def test_only_live_games_on_requested_date_qualify(self):
        self._game(date(2026, 10, 5), 'CLE', 'CWS', 'finished', 'MLB_done')
        live = self._game(date(2026, 10, 5), 'TBR', 'NYY', 'scheduled', 'MLB_849839')
        other_day = self._game(date(2026, 10, 4), 'SDP', 'CHC', 'scheduled', 'MLB_other')
        self.db.commit()

        qualifying = self.service._games_for_suggestions(date(2026, 10, 5))
        self.assertEqual([g.game_id for g in qualifying], [live.game_id])
        self.assertNotIn(other_day.game_id, [g.game_id for g in qualifying])
        self.assertEqual(set(SUGGESTABLE_GAME_STATUSES), {'scheduled', 'in_progress'})


if __name__ == '__main__':
    unittest.main()
