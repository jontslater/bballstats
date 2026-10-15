"""
Tests for MLB Statcast luck adjustment and MLBAM player mapping.
"""
import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.scrapers.mlb_api_client import MLBAPIClient
from app.scrapers.statcast_client import StatcastClient
from app.services.mlb_luck_adjustment import (
    apply_luck_to_mean,
    metrics_from_totals,
    luck_signal_for_stat,
)
from app.services.mlb_player_mapping import parse_boxscore_name, score_player_candidate, MlbamCandidate
from app.services.mlb_statcast_service import rollup_batted_ball_rows
from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.models.player import Player


def test_mlb_api_client_parses_mlbam_id():
    client = MLBAPIClient()
    parsed = client._parse_statsapi_batter(
        {
            "name": "Judge, A",
            "ab": "4",
            "h": "2",
            "doubles": "0",
            "triples": "0",
            "hr": "1",
            "rbi": "2",
            "personId": 592450,
        },
        "NYY",
    )
    assert parsed["mlbam_id"] == 592450
    assert parsed["total_bases"] == 5  # 1 single + 1 HR


def test_rollup_and_luck_signal_unlucky_hitter():
    rows = [
        {
            "batter_id": 123,
            "is_bip": True,
            "is_hit": False,
            "is_hr": False,
            "total_bases": 0,
            "est_ba": 0.62,
            "est_slg": 0.95,
            "est_woba": 0.55,
            "woba_value": 0.0,
            "woba_denom": 1.0,
            "launch_speed": 98.0,
            "launch_speed_angle": 6,
        },
        {
            "batter_id": 123,
            "is_bip": True,
            "is_hit": True,
            "is_hr": False,
            "total_bases": 1,
            "est_ba": 0.58,
            "est_slg": 0.80,
            "est_woba": 0.50,
            "woba_value": 0.88,
            "woba_denom": 1.0,
            "launch_speed": 88.0,
            "launch_speed_angle": 3,
        },
    ]
    rollups = rollup_batted_ball_rows(rows, date(2026, 4, 1), 2026)
    assert 123 in rollups
    payload = dict(rollups[123])
    payload["game_days"] = 1
    metrics = metrics_from_totals(payload)
    assert metrics["ba"] == 0.5
    assert metrics["xba"] > metrics["ba"]
    assert metrics["woba"] < metrics["xwoba"]
    assert luck_signal_for_stat("hits", metrics) > 0
    assert luck_signal_for_stat("home_runs", metrics) > 0


def test_apply_luck_increases_mean_for_unlucky_hitter():
    os.environ["MLB_LUCK_ADJUSTMENT"] = "1"
    metrics = {
        "bip": 40,
        "game_days": 15,
        "bip_per_game": 2.6,
        "ba": 0.250,
        "xba": 0.310,
        "slg": 0.400,
        "xslg": 0.520,
        "woba": 0.320,
        "xwoba": 0.390,
    }
    adjusted, debug = apply_luck_to_mean(0.85, "hits", metrics)
    assert debug["applied"] is True
    assert adjusted > 0.85
    assert debug["rel_change"] > 0


def test_calibrator_luck_changes_probability():
    os.environ["MLB_LUCK_ADJUSTMENT"] = "1"
    calc = CalibratedProbabilityCalculator(sport="MLB")
    metrics = {
        "bip": 50,
        "game_days": 20,
        "bip_per_game": 2.5,
        "ba": 0.24,
        "xba": 0.32,
        "slg": 0.38,
        "xslg": 0.52,
        "woba": 0.31,
        "xwoba": 0.40,
    }
    base = calc.calculate_probability_for_line(
        line=0.5,
        player_mean=0.82,
        player_std=0.5,
        sample_size=20,
        stat_type="hits",
        league_mean=0.81,
        luck_metrics=metrics,
        luck_adjustment_enabled=False,
    )
    lucky = calc.calculate_probability_for_line(
        line=0.5,
        player_mean=0.82,
        player_std=0.5,
        sample_size=20,
        stat_type="hits",
        league_mean=0.81,
        luck_metrics=metrics,
        luck_adjustment_enabled=True,
        luck_weight=0.35,
    )
    assert lucky["probability"] != base["probability"]


def test_statcast_client_parses_bip_row():
    client = StatcastClient(delay=0)
    row = {
        "batter": "592450",
        "events": "single",
        "launch_speed": "101.2",
        "estimated_ba_using_speedangle": "0.820",
        "estimated_slg_using_speedangle": "1.050",
        "estimated_woba_using_speedangle": "0.780",
        "woba_value": "0.890",
        "woba_denom": "1",
        "launch_speed_angle": "6",
        "game_date": "2026-04-01",
    }
    parsed = client._normalize_row(row)
    assert parsed["is_bip"] is True
    assert parsed["batter_id"] == 592450
    assert parsed["is_hit"] is True


def test_link_player_mlbam_id_conflict_safe():
    from app.services.mlb_statcast_service import link_player_mlbam_id

    player = MagicMock()
    player.player_id = 99
    player.mlbam_id = None
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(player_id=1)
    assert link_player_mlbam_id(db, player, 592450) is False
    assert player.mlbam_id is None


def test_parse_boxscore_name_and_team_scoring():
    last, first = parse_boxscore_name("Murphy, C")
    assert last == "murphy"
    assert first == "c"
    player = Player(sport="MLB", name="Murphy, C", player_id=1)
    cand = MlbamCandidate(
        mlbam_id=123,
        full_name="Caleb Murphy",
        last_name="murphy",
        first_initial="c",
        boxscore_name="Murphy",
        team_abbrev="HOU",
    )
    score = score_player_candidate(player, cand, team_abbrev="HOU")
    assert score >= 4.0


def test_name_matching_distinguishes_marsh_candidates():
    player = Player(sport="MLB", name="Marsh", player_id=1)
    brandon = MlbamCandidate(
        mlbam_id=669016,
        full_name="Brandon Marsh",
        last_name="marsh",
        first_initial="b",
        boxscore_name="Marsh",
        team_abbrev="PHI",
    )
    other = MlbamCandidate(
        mlbam_id=111,
        full_name="Other Marsh",
        last_name="marsh",
        first_initial="x",
        boxscore_name="Marsh",
        team_abbrev="NYM",
    )
    assert score_player_candidate(player, brandon, "PHI") > score_player_candidate(player, other, "PHI")
