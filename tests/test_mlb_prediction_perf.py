#!/usr/bin/env python3
"""
Guards for MLB prediction generation performance and replace-on-rerun.

Root cause of the daily hang: PredictionAdjustments called NBA
PaceCalculator.calculate_team_pace (and league-average pace, which scans
every team) on every MLB player/stat. That was an N+1 over every finished
team game × player_game_stats (~4,900 games / ~140k rows on Jonathan's DB).
"""
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

backend_path = Path(__file__).parent.parent / "backend"
scripts_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(backend_path))
sys.path.insert(0, str(scripts_path))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (  # noqa: F401
    Team, Season, Player, Game, PlayerGameStat, Injury, TeamPositionDefense,
    PlayerTeamMatchup, InjuryImpactHistory, Prediction, GameSchedule, UserPlay,
    Lineup, BettingLine, Parlay, PoorMansBetChallenge, PoorMansBetDay,
    ValueLadder, HistoricalSuggestedBet, HistoricalParlay, HistoricalParlayLeg,
)
from app.services.pace_calculator import PaceCalculator
from app.services.league_averages import LeagueAverages
from app.services.prediction_adjustments import PredictionAdjustments
from app.services.prediction_service import PredictionService

import generate_mlb_predictions as mlb_pred


class QueryCounter:
    def __init__(self, engine):
        self.engine = engine
        self.count = 0
        event.listen(engine, "before_cursor_execute", self._on_execute)

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):
        self.count += 1

    def reset(self):
        self.count = 0

    def close(self):
        event.remove(self.engine, "before_cursor_execute", self._on_execute)


def _session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)()


def _nba_box(fga, fta, turnovers):
    return {
        'field_goals_attempted': fga,
        'free_throws_attempted': fta,
        'turnovers': turnovers,
        'minutes_played': 20,
        'points': 10,
    }


class TestPaceCalculatorPerf(unittest.TestCase):
    def setUp(self):
        self.engine, self.db = _session()
        self.counter = QueryCounter(self.engine)
        self.home = Team(sport='NBA', name='Lakers', abbreviation='LAL', conference='West')
        self.away = Team(sport='NBA', name='Celtics', abbreviation='BOS', conference='East')
        self.db.add_all([self.home, self.away])
        self.db.flush()
        self.season = Season(sport='NBA', season_year='2025-26', is_current=True)
        self.db.add(self.season)
        self.db.flush()
        self.players = []
        for i in range(5):
            p = Player(sport='NBA', name=f'Player {i}', position='SG', current_team_id=self.home.team_id)
            self.db.add(p)
            self.db.flush()
            self.players.append(p)

    def tearDown(self):
        self.counter.close()
        self.db.close()

    def _seed_finished_games(self, n_games, box=_nba_box(80, 20, 12)):
        games = []
        start = date(2025, 11, 1)
        for i in range(n_games):
            g = Game(
                sport='NBA',
                game_date=start + timedelta(days=i),
                season_id=self.season.season_id,
                home_team_id=self.home.team_id,
                away_team_id=self.away.team_id,
                game_status='finished',
                home_score=100,
                away_score=98,
            )
            self.db.add(g)
            self.db.flush()
            games.append(g)
            for player in self.players:
                self.db.add(PlayerGameStat(
                    sport='NBA',
                    player_id=player.player_id,
                    game_id=g.game_id,
                    team_id=self.home.team_id,
                    opponent_team_id=self.away.team_id,
                    is_home=True,
                    **box,
                ))
        self.db.commit()
        return games

    def test_team_pace_matches_original_formula(self):
        self._seed_finished_games(8, box=_nba_box(80, 20, 12))
        # 5 players × (80, 20, 12) per game
        possessions = (5 * 80 + 0.44 * 5 * 20 + 5 * 12) / 2
        expected = round(possessions, 2)
        pace = PaceCalculator(self.db).calculate_team_pace(self.home.team_id, self.season.season_id)
        self.assertEqual(pace, expected)

    def test_team_pace_is_cached_and_not_n_plus_one(self):
        n_games = 40
        self._seed_finished_games(n_games)
        calc = PaceCalculator(self.db)

        self.counter.reset()
        first = calc.calculate_team_pace(self.home.team_id, self.season.season_id)
        first_queries = self.counter.count
        self.assertIsNotNone(first)
        # Old path: 1 games query + 1 player-stat query per game (>= n_games).
        self.assertLess(first_queries, n_games, msg=f"team pace used {first_queries} queries for {n_games} games")

        self.counter.reset()
        second = calc.calculate_team_pace(self.home.team_id, self.season.season_id)
        self.assertEqual(first, second)
        self.assertEqual(self.counter.count, 0)

    def test_league_avg_pace_reuses_shared_calculator_cache(self):
        self._seed_finished_games(12)
        pace_calc = PaceCalculator(self.db)
        avgs = LeagueAverages(self.db, pace_calculator=pace_calc)

        self.counter.reset()
        first = avgs.calculate_league_avg_pace(self.season.season_id)
        first_queries = self.counter.count
        self.assertGreater(first, 0)

        self.counter.reset()
        second = avgs.calculate_league_avg_pace(self.season.season_id)
        self.assertEqual(first, second)
        self.assertEqual(self.counter.count, 0)
        self.assertLess(first_queries, 40)


class TestMlbAdjustmentsSkipNbaPace(unittest.TestCase):
    def setUp(self):
        self.engine, self.db = _session()
        self.home = Team(sport='MLB', name='Yankees', abbreviation='NYY', conference='AL')
        self.away = Team(sport='MLB', name='Red Sox', abbreviation='BOS', conference='AL')
        self.db.add_all([self.home, self.away])
        self.db.flush()
        self.season = Season(sport='MLB', season_year='2026', is_current=True)
        self.db.add(self.season)
        self.db.flush()
        self.player = Player(
            sport='MLB', name='Aaron Judge', position='RF', current_team_id=self.home.team_id
        )
        self.db.add(self.player)
        self.db.flush()

        start = date(2026, 4, 1)
        for i in range(80):
            g = Game(
                sport='MLB',
                game_date=start + timedelta(days=i),
                season_id=self.season.season_id,
                home_team_id=self.home.team_id,
                away_team_id=self.away.team_id,
                game_status='finished',
                home_score=5,
                away_score=3,
            )
            self.db.add(g)
            self.db.flush()
            self.db.add(PlayerGameStat(
                sport='MLB',
                player_id=self.player.player_id,
                game_id=g.game_id,
                team_id=self.home.team_id,
                opponent_team_id=self.away.team_id,
                is_home=True,
                hits=2,
                home_runs=1,
                total_bases=5,
            ))
        upcoming = Game(
            sport='MLB',
            game_date=date(2026, 7, 1),
            season_id=self.season.season_id,
            home_team_id=self.home.team_id,
            away_team_id=self.away.team_id,
            game_status='scheduled',
        )
        self.db.add(upcoming)
        self.db.flush()
        self.upcoming = upcoming
        self.db.commit()
        self.counter = QueryCounter(self.engine)

    def tearDown(self):
        self.counter.close()
        self.db.close()

    def test_mlb_mean_adjustments_do_not_call_nba_pace(self):
        adj = PredictionAdjustments(self.db, sport='MLB')
        calls = {'team': 0, 'recent': 0, 'league': 0}

        orig_team = adj.pace_calc.calculate_team_pace
        orig_recent = adj.pace_calc.calculate_recent_team_pace
        orig_league = adj.league_avg.calculate_league_avg_pace

        def team(*args, **kwargs):
            calls['team'] += 1
            return orig_team(*args, **kwargs)

        def recent(*args, **kwargs):
            calls['recent'] += 1
            return orig_recent(*args, **kwargs)

        def league(*args, **kwargs):
            calls['league'] += 1
            return orig_league(*args, **kwargs)

        adj.pace_calc.calculate_team_pace = team
        adj.pace_calc.calculate_recent_team_pace = recent
        adj.league_avg.calculate_league_avg_pace = league

        result = adj.calculate_mean_adjustments(
            base_mean=1.2,
            player_id=self.player.player_id,
            opponent_team_id=self.away.team_id,
            projected_minutes=4.0,
            historical_avg_minutes=4.0,
            is_home=True,
            player_position='RF',
            season_id=self.season.season_id,
            stat_type='hits',
            game_id=self.upcoming.game_id,
        )
        self.assertEqual(calls, {'team': 0, 'recent': 0, 'league': 0})
        self.assertEqual(result['pace_factor'], 1.0)
        self.assertEqual(result['foul_trouble_factor'], 1.0)
        self.assertEqual(result['advanced_analytics_factor'], 1.0)

    def test_mlb_mean_adjustments_query_budget_does_not_scan_every_game(self):
        """Scaled-down desktop DB: 80 finished games. Pace N+1 would be 80+ queries."""
        adj = PredictionAdjustments(self.db, sport='MLB')
        self.counter.reset()
        adj.calculate_mean_adjustments(
            base_mean=1.2,
            player_id=self.player.player_id,
            opponent_team_id=self.away.team_id,
            projected_minutes=4.0,
            historical_avg_minutes=4.0,
            is_home=True,
            player_position='RF',
            season_id=self.season.season_id,
            stat_type='hits',
            game_id=self.upcoming.game_id,
        )
        first = self.counter.count
        self.assertLess(
            first,
            80,
            msg=f"MLB adjustments issued {first} queries — still scanning the season?",
        )

        self.counter.reset()
        adj.calculate_mean_adjustments(
            base_mean=1.2,
            player_id=self.player.player_id,
            opponent_team_id=self.away.team_id,
            projected_minutes=4.0,
            historical_avg_minutes=4.0,
            is_home=True,
            player_position='RF',
            season_id=self.season.season_id,
            stat_type='hits',
            game_id=self.upcoming.game_id,
        )
        self.assertLessEqual(self.counter.count, first)


class TestMlbPredictionReplace(unittest.TestCase):
    def setUp(self):
        self.engine, self.db = _session()
        self.home = Team(sport='MLB', name='Yankees', abbreviation='NYY', conference='AL')
        self.away = Team(sport='MLB', name='Red Sox', abbreviation='BOS', conference='AL')
        self.db.add_all([self.home, self.away])
        self.db.flush()
        self.season = Season(sport='MLB', season_year='2026', is_current=True)
        self.db.add(self.season)
        self.db.flush()
        self.player = Player(
            sport='MLB', name='Aaron Judge', position='RF', current_team_id=self.home.team_id
        )
        self.db.add(self.player)
        self.db.flush()
        self.game = Game(
            sport='MLB',
            game_date=date(2026, 10, 9),
            season_id=self.season.season_id,
            home_team_id=self.home.team_id,
            away_team_id=self.away.team_id,
            game_status='scheduled',
        )
        self.db.add(self.game)
        self.db.flush()

    def tearDown(self):
        self.db.close()

    def _add_pred(self, bet_type='safe', stat_type='hits', mean=1.1):
        pred = Prediction(
            sport='MLB',
            player_id=self.player.player_id,
            game_id=self.game.game_id,
            stat_type=stat_type,
            bet_type=bet_type,
            distribution_mean=mean,
            safe_line=0.5,
        )
        self.db.add(pred)
        self.db.flush()
        return pred

    def test_replace_existing_mlb_predictions_clears_game(self):
        self._add_pred('safe')
        self._add_pred('standard')
        self._add_pred('safe', stat_type='home_runs')
        self.db.commit()
        self.assertEqual(self.db.query(Prediction).count(), 3)

        deleted = mlb_pred.replace_existing_mlb_predictions(self.db, self.game.game_id)
        self.db.commit()
        self.assertEqual(deleted, 3)
        self.assertEqual(self.db.query(Prediction).count(), 0)

    def test_rerun_does_not_accumulate_player_game_stat_prediction_rows(self):
        self._add_pred('safe')
        self._add_pred('standard')
        self.db.commit()

        mlb_pred.replace_existing_mlb_predictions(self.db, self.game.game_id)
        self.db.commit()
        self._add_pred('safe', mean=1.4)
        self.db.commit()

        rows = self.db.query(Prediction).filter(
            Prediction.player_id == self.player.player_id,
            Prediction.game_id == self.game.game_id,
            Prediction.stat_type == 'hits',
        ).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].distribution_mean, 1.4)

    def test_generate_predictions_for_game_replaces_before_running(self):
        self._add_pred('safe')
        self._add_pred('long_shot')
        self.db.commit()

        from unittest.mock import patch
        with patch.object(PredictionService, 'generate_prediction', return_value=None):
            mlb_pred.generate_predictions_for_game(self.db, self.game.game_id)

        self.assertEqual(
            self.db.query(Prediction).filter(Prediction.game_id == self.game.game_id).count(),
            0,
        )

    def test_prediction_service_replace_is_sport_scoped(self):
        self._add_pred('safe')
        nba_player = Player(sport='NBA', name='LeBron', position='SF', current_team_id=self.home.team_id)
        self.db.add(nba_player)
        self.db.flush()
        self.db.add(Prediction(
            sport='NBA',
            player_id=nba_player.player_id,
            game_id=self.game.game_id,
            stat_type='points',
            bet_type='safe',
            distribution_mean=25.0,
        ))
        self.db.commit()

        deleted = PredictionService(self.db, sport='MLB').replace_predictions_for_game(self.game.game_id)
        self.db.commit()
        self.assertEqual(deleted, 1)
        remaining = self.db.query(Prediction).all()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].sport, 'NBA')


if __name__ == '__main__':
    unittest.main()
