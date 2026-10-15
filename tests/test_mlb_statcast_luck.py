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
from app.services.mlb_statcast_service import rollup_batted_ball_rows
from app.services.calibrated_probability import CalibratedProbabilityCalculator


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
            "total_bases": 0,
            "est_ba": 0.62,
            "est_slg": 0.95,
            "est_woba": 0.55,
            "launch_speed": 98.0,
            "launch_speed_angle": 6,
        },
        {
            "batter_id": 123,
            "is_bip": True,
            "is_hit": True,
            "total_bases": 1,
            "est_ba": 0.58,
            "est_slg": 0.80,
            "est_woba": 0.50,
            "launch_speed": 88.0,
            "launch_speed_angle": 3,
        },
    ]
    rollups = rollup_batted_ball_rows(rows, date(2026, 4, 1), 2026)
    assert 123 in rollups
    assert rollups[123]["bip"] == 2
    metrics = metrics_from_totals(rollups[123])
    assert metrics["ba"] == 0.5
    assert metrics["xba"] > metrics["ba"]
    assert luck_signal_for_stat("hits", metrics) > 0


def test_apply_luck_increases_mean_for_unlucky_hitter():
    os.environ["MLB_LUCK_ADJUSTMENT"] = "1"
    metrics = {"bip": 40, "ba": 0.250, "xba": 0.290, "slg": 0.400, "xslg": 0.480, "woba": 0.320, "xwoba": 0.360}
    adjusted, debug = apply_luck_to_mean(0.85, "hits", metrics)
    assert debug["applied"] is True
    assert adjusted > 0.85


def test_calibrator_applies_luck_when_enabled():
    os.environ["MLB_LUCK_ADJUSTMENT"] = "1"
    calc = CalibratedProbabilityCalculator(sport="MLB")
    metrics = {"bip": 50, "ba": 0.24, "xba": 0.30, "slg": 0.38, "xslg": 0.50, "woba": 0.31, "xwoba": 0.38}
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
    )
    assert lucky["probability"] >= base["probability"]


def test_statcast_client_parses_bip_row():
    client = StatcastClient(delay=0)
    row = {
        "batter": "592450",
        "events": "single",
        "launch_speed": "101.2",
        "estimated_ba_using_speedangle": "0.820",
        "estimated_slg_using_speedangle": "1.050",
        "estimated_woba_using_speedangle": "0.780",
        "launch_speed_angle": "6",
        "game_date": "2026-04-01",
    }
    parsed = client._normalize_row(row)
    assert parsed["is_bip"] is True
    assert parsed["batter_id"] == 592450
    assert parsed["is_hit"] is True


def test_link_player_mlbam_id_updates_statcast_rows():
    from app.services.mlb_statcast_service import link_player_mlbam_id

    player = MagicMock()
    player.player_id = 99
    player.mlbam_id = None
    db = MagicMock()
    link_player_mlbam_id(db, player, 592450)
    assert player.mlbam_id == 592450
    db.query.return_value.filter.return_value.update.assert_called_once()
