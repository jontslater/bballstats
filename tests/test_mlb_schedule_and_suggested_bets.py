#!/usr/bin/env python3
"""
Tests for MLB postseason schedule persistence, lookback reconcile, results
backfill, and suggested-bets date scoping.

Covers:
  (a) postseason schedule inclusion (gameType F/D/L/W) without duplicating games
  (b) empty-date returns empty suggestions
  (c) finished series games are not suggested for a later date
  (d) dropped if-necessary / Unknown games are cancelled and excluded from suggestions
  (e) missed-day finals are backfilled by espn_game_id; re-run is idempotent
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
    mlb_game_status,
    persist_mlb_schedule_games,
    reconcile_mlb_schedule_window,
)
from app.services.mlb_results import collect_games_for_date
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
        ('ATL', 'Atlanta Braves', 144),
        ('LAD', 'Los Angeles Dodgers', 119),
        ('MIL', 'Milwaukee Brewers', 158),
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

    def test_unknown_and_cancelled_api_status_map_to_cancelled(self):
        self.assertEqual(mlb_game_status('Unknown'), 'cancelled')
        self.assertEqual(mlb_game_status('Cancelled'), 'cancelled')
        self.assertEqual(mlb_game_status('Canceled'), 'cancelled')
        self.assertEqual(mlb_game_status('Postponed'), 'cancelled')
        self.assertEqual(mlb_game_status('Final'), 'finished')
        self.assertEqual(mlb_game_status('Pre-Game'), 'scheduled')

        persist_mlb_schedule_games(
            self.db,
            [_api_game(849837, '2026-10-08', 'D', 'Unknown', 147, 139)],
            self.season,
        )
        self.db.commit()
        game = self.db.query(Game).one()
        self.assertEqual(game.game_status, 'cancelled')
        self.assertEqual(game.espn_game_id, 'MLB_849837')
        self.assertEqual(self.db.query(GameSchedule).one().status, 'cancelled')

    def test_dropped_if_necessary_game_is_cancelled_not_deleted(self):
        """Series-clinched if-necessary game vanishes from the Stats API schedule."""
        persist_mlb_schedule_games(
            self.db,
            [
                _api_game(849837, '2026-10-08', 'D', 'Scheduled', 147, 139),  # NYY @ TBR if nec
                _api_game(849824, '2026-10-09', 'D', 'Scheduled', 135, 158),  # SDP @ MIL
                _api_game(849821, '2026-10-09', 'D', 'Scheduled', 144, 119),  # ATL @ LAD
                _api_game(849836, '2026-10-10', 'D', 'Scheduled', 139, 147),  # TBR @ NYY
                _api_game(849838, '2026-10-07', 'D', 'Final', 139, 147),  # real final
            ],
            self.season,
        )
        self.db.commit()
        self.assertEqual(self.db.query(Game).filter(Game.sport == 'MLB').count(), 5)

        # Later sync: if-necessary games are gone; Oct 7 final remains.
        still_listed = [
            _api_game(849838, '2026-10-07', 'D', 'Final', 139, 147),
            _api_game(849831, '2026-10-10', 'D', 'Scheduled', 145, 114),  # real Game 5 CWS @ CLE
        ]
        persist_mlb_schedule_games(self.db, still_listed, self.season)
        rec = reconcile_mlb_schedule_window(
            self.db, still_listed, date(2026, 10, 1), date(2026, 10, 12)
        )
        self.db.commit()

        self.assertEqual(rec['cancelled_games'], 4)
        by_id = {g.espn_game_id: g for g in self.db.query(Game).filter(Game.sport == 'MLB').all()}
        self.assertEqual(len(by_id), 6)  # 5 original + CLE/CWS Game 5; nothing deleted
        for pk in ('MLB_849837', 'MLB_849824', 'MLB_849821', 'MLB_849836'):
            self.assertEqual(by_id[pk].game_status, 'cancelled', pk)
        self.assertEqual(by_id['MLB_849838'].game_status, 'finished')
        self.assertEqual(by_id['MLB_849831'].game_status, 'scheduled')

        rec2 = reconcile_mlb_schedule_window(
            self.db, still_listed, date(2026, 10, 1), date(2026, 10, 12)
        )
        self.db.commit()
        self.assertEqual(rec2['cancelled_games'], 0)
        self.assertEqual(self.db.query(Game).filter(Game.sport == 'MLB').count(), 6)

    def test_reconcile_does_not_void_finished_historical_games(self):
        persist_mlb_schedule_games(
            self.db,
            [_api_game(849838, '2026-10-07', 'D', 'Final', 139, 147)],
            self.season,
        )
        game = self.db.query(Game).one()
        game.home_score = 3
        game.away_score = 4
        self.db.commit()

        rec = reconcile_mlb_schedule_window(
            self.db, [], date(2026, 10, 1), date(2026, 10, 12)
        )
        self.db.commit()
        self.assertEqual(rec['cancelled_games'], 0)
        game = self.db.query(Game).one()
        self.assertEqual(game.game_status, 'finished')
        self.assertEqual(game.home_score, 3)
        self.assertEqual(game.away_score, 4)


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

    def test_cancelled_and_void_games_never_suggested(self):
        cancelled = self._game(date(2026, 10, 9), 'MIL', 'SDP', 'cancelled', 'MLB_849824')
        voided = self._game(date(2026, 10, 9), 'LAD', 'ATL', 'void', 'MLB_849821')
        player = Player(
            sport='MLB',
            name='Manny Machado',
            position='3B',
            current_team_id=self.teams['SDP'].team_id,
        )
        self.db.add(player)
        self.db.flush()
        for game in (cancelled, voided):
            self.db.add(Prediction(
                sport='MLB',
                player_id=player.player_id,
                game_id=game.game_id,
                stat_type='hits',
                bet_type='safe',
                safe_line=0.5,
                safe_probability=0.92,
                confidence_level='HIGH',
            ))
        self.db.commit()

        qualifying = self.service._games_for_suggestions(date(2026, 10, 9))
        self.assertEqual(qualifying, [])
        self.assertEqual(self.service.get_suggested_bets(game_date=date(2026, 10, 9)), [])
        self.assertNotIn('cancelled', SUGGESTABLE_GAME_STATUSES)
        self.assertNotIn('void', SUGGESTABLE_GAME_STATUSES)


class FakeMLBResultsClient:
    """Minimal stand-in for MLBAPIClient used by collect_games_for_date."""

    def __init__(self, games, parsed_by_pk):
        self.games = games
        self.parsed_by_pk = parsed_by_pk
        self.box_score_calls = []

    def get_schedule(self, game_date=None, start_date=None, end_date=None):
        return list(self.games)

    def get_team_abbrev(self, mlb_team_id):
        from app.scrapers.mlb_api_client import MLB_TEAM_ID_TO_ABBREV
        return MLB_TEAM_ID_TO_ABBREV.get(mlb_team_id)

    def get_box_score_data(self, game_id):
        self.box_score_calls.append(game_id)
        if game_id not in self.parsed_by_pk:
            return None
        return {'game_id': game_id}

    def parse_box_score_for_db(self, box_data, home_abbrev, away_abbrev):
        return self.parsed_by_pk[box_data['game_id']]


class TestMlbResultsBackfill(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        self.teams, self.season = _seed_mlb(self.db)

    def tearDown(self):
        self.db.close()

    def _scheduled_game(self, game_pk, game_date, away_abbr, home_abbr):
        g = Game(
            sport='MLB',
            game_date=game_date,
            season_id=self.season.season_id,
            home_team_id=self.teams[home_abbr].team_id,
            away_team_id=self.teams[away_abbr].team_id,
            game_status='scheduled',
            espn_game_id=f'MLB_{game_pk}',
        )
        self.db.add(g)
        self.db.flush()
        return g

    def test_missed_day_final_is_backfilled_by_espn_game_id(self):
        """Oct 7 game still scheduled (missed --previous-day) is matched by MLB_<gamePk>."""
        existing = self._scheduled_game(849838, date(2026, 10, 7), 'TBR', 'NYY')
        self.db.commit()

        parsed = {
            'away_score': 4,
            'home_score': 3,
            'player_stats': [
                {
                    'player_name': 'Aaron Judge',
                    'team_abbreviation': 'NYY',
                    'is_batter': True,
                    'is_pitcher': False,
                    'at_bats': 4,
                    'plate_appearances': 4,
                    'hits': 2,
                    'doubles': 0,
                    'triples': 0,
                    'home_runs': 1,
                    'total_bases': 5,
                    'rbis': 2,
                },
                {
                    'player_name': 'Shane McClanahan',
                    'team_abbreviation': 'TBR',
                    'is_batter': False,
                    'is_pitcher': True,
                    'innings_pitched': 5.0,
                    'strikeouts': 8,
                    'hits_allowed': 4,
                    'walks_allowed': 1,
                },
            ],
        }
        api_game = _api_game(849838, '2026-10-07', 'D', 'Final', 139, 147)
        api_game['away_score'] = 4
        api_game['home_score'] = 3
        client = FakeMLBResultsClient([api_game], {849838: parsed})

        created, processed = collect_games_for_date(self.db, client, date(2026, 10, 7))
        self.assertEqual(created, 0)
        self.assertEqual(processed, 1)
        self.assertEqual(self.db.query(Game).filter(Game.sport == 'MLB').count(), 1)

        game = self.db.query(Game).filter(Game.espn_game_id == 'MLB_849838').one()
        self.assertEqual(game.game_id, existing.game_id)
        self.assertEqual(game.game_status, 'finished')
        self.assertEqual(game.away_score, 4)
        self.assertEqual(game.home_score, 3)

        stats = self.db.query(PlayerGameStat).filter(PlayerGameStat.game_id == game.game_id).all()
        self.assertEqual(len(stats), 2)
        by_player = {}
        for s in stats:
            name = self.db.query(Player).filter(Player.player_id == s.player_id).one().name
            by_player[name] = s
        self.assertEqual(by_player['Aaron Judge'].home_runs, 1)
        self.assertEqual(by_player['Aaron Judge'].total_bases, 5)
        self.assertEqual(by_player['Shane McClanahan'].strikeouts, 8)

        # Re-run is idempotent: no duplicate Game or PlayerGameStat rows, no extra box calls needed.
        created2, processed2 = collect_games_for_date(self.db, client, date(2026, 10, 7))
        self.assertEqual(created2, 0)
        self.assertEqual(self.db.query(Game).filter(Game.sport == 'MLB').count(), 1)
        self.assertEqual(
            self.db.query(PlayerGameStat).filter(PlayerGameStat.game_id == game.game_id).count(),
            2,
        )
        # Second pass short-circuits before another box-score fetch.
        self.assertEqual(client.box_score_calls, [849838])
        self.assertEqual(processed2, 1)


if __name__ == '__main__':
    unittest.main()

