#!/usr/bin/env python3
"""Verify tests ignore a toxic local nba_prop_calibration.json."""
import os
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import sys

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.nba_prop_calibration_store import (
    calibration_override,
    get_prob_shrink,
)
from app.services.nba_sportsbook_edge import PROB_CLAMP_HIGH, probability_over_line


class TestCalibrationJsonIsolation(unittest.TestCase):
    def test_autouse_fixture_uses_neutral_calibration(self):
        self.assertEqual(get_prob_shrink(), 1.0)
        p = probability_over_line(
            40.0, 20.0, 10.0, stat_type="points", calibrate=True
        )
        self.assertEqual(p, PROB_CLAMP_HIGH)

    def test_override_context_temporary(self):
        with calibration_override({"prob_shrink": 0.3, "prob_sigma_scale": 1.0}):
            p = probability_over_line(
                40.0, 20.0, 10.0, stat_type="points", calibrate=True
            )
            self.assertLess(p, PROB_CLAMP_HIGH)
        p2 = probability_over_line(
            40.0, 20.0, 10.0, stat_type="points", calibrate=True
        )
        self.assertEqual(p2, PROB_CLAMP_HIGH)


if __name__ == "__main__":
    unittest.main()
