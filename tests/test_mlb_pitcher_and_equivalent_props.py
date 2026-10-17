#!/usr/bin/env python3
"""MLB probable-starter pitcher props and hits/TB OVER 0.5 equivalence."""
import os
import sys
import unittest
from datetime import date
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

backend_path = Path(__file__).parent.parent / 'backend'
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Team, Season, Player, Game, Prediction
from app.models import (  # noqa: F401
    PlayerGameStat, Injury, TeamPositionDefense, PlayerTeamMatchup,
    InjuryImpactHistory, GameSchedule, UserPlay, Lineup, BettingLine,
    Parlay, PoorMansBetChallenge, PoorMansBetDay, ValueLadder,
    HistoricalSuggestedBet, HistoricalParlay, HistoricalParlayLeg,
)
from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.services.mlb_equivalent_props import (
    apply_canonical_hit_over_half_probabilities,
    is_hit_or_tb_over_half,
    suggested_bet_dedup_key,
)
from app.services.mlb_probable_pitchers import (
    MlbProbablePitcherResolver,
    normalize_mlb_person_name,
    should_skip_mlb_pitcher_prop,
)
from app.services.suggested_bets import SuggestedBetsService


def _session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class FakeScheduleClient:
    def __init__(self, rows_by_date):
        self.rows_by_date = rows_by_date

    def get_schedule(self, game_date=None, start_date=None, end_date=None):
        if game_date is None:
            return []
        return self.rows_by_date.get(game_date, [])


class TestMlbProbablePitcherFilter(unittest.TestCase):
    def setUp(self):
        self.db = _session()
        home = Team(sport='MLB', name='Cleveland Guardians', abbreviation='CLE', conference='AL', division='Central')
        away = Team(sport='MLB', name='Tampa Bay Rays', abbreviation='TBR', conference='AL', division='East')
        self.db.add_all([home, away])
        self.db.flush()
        season = Season(sport='MLB', season_year='2026', is_current=True)
        self.db.add(season)
        self.db.flush()
        self.game = Game(
            sport='MLB',
            game_date=date(2026, 10, 17),
            season_id=season.season_id,
            home_team_id=home.team_id,
            away_team_id=away.team_id,
            game_status='scheduled',
            espn_game_id='MLB_849816',
        )
        self.db.add(self.game)
        mc = Player(sport='MLB', name='Shane McClanahan', position='SP', current_team_id=away.team_id)
        nick = Player(sport='MLB', name='Nick Martinez', position='SP', current_team_id=away.team_id)
        self.db.add_all([mc, nick])
        self.db.commit()
        self.mc = mc
        self.nick = nick
        self.client = FakeScheduleClient({
            date(2026, 10, 17): [{
                'game_id': 849816,
                'home_id': 114,
                'away_id': 139,
                'home_probable_pitcher': 'Shawn Armstrong',
                'away_probable_pitcher': 'Nick Martinez',
            }],
        })
        self.resolver = MlbProbablePitcherResolver(client=self.client)

    def tearDown(self):
        self.db.close()

    def test_non_probable_starter_skipped_for_strikeouts(self):
        self.assertTrue(
            should_skip_mlb_pitcher_prop(
                self.db, self.game, self.mc, 'strikeouts', self.resolver
            )
        )
        self.assertFalse(
            should_skip_mlb_pitcher_prop(
                self.db, self.game, self.nick, 'strikeouts', self.resolver
            )
        )

    def test_no_probable_listed_skips_all_pitcher_props(self):
        empty_client = FakeScheduleClient({
            date(2026, 10, 17): [{
                'game_id': 849816,
                'home_id': 114,
                'away_id': 139,
                'home_probable_pitcher': '',
                'away_probable_pitcher': '',
            }],
        })
        resolver = MlbProbablePitcherResolver(client=empty_client)
        self.assertTrue(
            should_skip_mlb_pitcher_prop(
                self.db, self.game, self.nick, 'strikeouts', resolver
            )
        )

    def test_name_normalization(self):
        self.assertEqual(
            normalize_mlb_person_name("J.P. Smith"),
            normalize_mlb_person_name('JP Smith'),
        )


class TestHitTbOverHalfEquivalence(unittest.TestCase):
    def test_dedup_key_collapses_hits_and_total_bases(self):
        k1 = suggested_bet_dedup_key(1, 'hits', 0.5)
        k2 = suggested_bet_dedup_key(1, 'total_bases', 0.5)
        self.assertEqual(k1, k2)
        self.assertTrue(is_hit_or_tb_over_half('total_bases', 0.5))

    def test_canonical_probability_matches_for_both_stat_types(self):
        calc = CalibratedProbabilityCalculator(sport='MLB')
        profile = {
            'mean': 1.05,
            'std': 0.9,
            'sample_size': 20,
            'league_mean': 0.81,
        }
        hits_lines = {
            'safe_line': 0.5,
            'safe_probability': 0.0,
            'standard_line': 1.5,
            'standard_probability': 0.4,
        }
        tb_lines = {
            'safe_line': 0.5,
            'safe_probability': 0.99,
            'standard_line': 1.5,
            'standard_probability': 0.4,
        }
        apply_canonical_hit_over_half_probabilities(calc, hits_lines, profile)
        apply_canonical_hit_over_half_probabilities(calc, tb_lines, profile)
        self.assertEqual(hits_lines['safe_probability'], tb_lines['safe_probability'])
        self.assertNotEqual(hits_lines['standard_probability'], 0.99)

    def test_suggested_bets_dedupes_hits_and_total_bases_over_half(self):
        db = _session()
        home = Team(sport='MLB', name='A', abbreviation='AAA', conference='AL', division='E')
        away = Team(sport='MLB', name='B', abbreviation='BBB', conference='AL', division='E')
        db.add_all([home, away])
        db.flush()
        season = Season(sport='MLB', season_year='2026', is_current=True)
        db.add(season)
        db.flush()
        player = Player(sport='MLB', name='Test Batter', position='OF', current_team_id=home.team_id)
        db.add(player)
        db.flush()
        game = Game(
            sport='MLB',
            game_date=date(2026, 10, 17),
            season_id=season.season_id,
            home_team_id=home.team_id,
            away_team_id=away.team_id,
            game_status='scheduled',
            espn_game_id='MLB_999001',
        )
        db.add(game)
        db.flush()
        for stat_type, prob in (('hits', 0.638), ('total_bases', 0.655)):
            db.add(
                Prediction(
                    sport='MLB',
                    player_id=player.player_id,
                    game_id=game.game_id,
                    stat_type=stat_type,
                    bet_type='safe',
                    safe_line=0.5,
                    safe_probability=prob,
                    standard_line=1.5,
                    standard_probability=0.3,
                    distribution_mean=1.0,
                    distribution_std_dev=0.5,
                    confidence_level='MEDIUM',
                    confidence_score=50,
                    line_source='model',
                )
            )
        db.commit()

        service = SuggestedBetsService(db, sport='MLB')
        bets = service.get_suggested_bets(game_date=date(2026, 10, 17), limit=50)
        over_half = [
            b
            for b in bets
            if b['player_id'] == player.player_id
            and b['line'] == 0.5
            and b['stat_type'] in ('hits', 'total_bases')
        ]
        self.assertEqual(len(over_half), 1)
        self.assertEqual(over_half[0]['stat_type'], 'hits')
        db.close()


if __name__ == '__main__':
    unittest.main()
