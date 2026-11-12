"""Pytest hooks shared across the test suite."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

backend_path = Path(__file__).parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.services.nba_prop_calibration_store import reset_calibration_cache, set_calibration_override

_DEFAULT_CALIB = {
    "fit_season": None,
    "tier_subtract": {},
    "prob_shrink": 1.0,
    "prob_sigma_scale": 1.0,
}


@pytest.fixture(autouse=True)
def _isolate_nba_prop_calibration_json():
    """Ignore a developer's local nba_prop_calibration.json during tests."""
    set_calibration_override(_DEFAULT_CALIB)
    yield
    set_calibration_override(None)
    reset_calibration_cache()
