"""Sanity helpers for luck backtest comparison."""
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Import backtest helpers from script module path
scripts_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

from backtest_calibration import count_prediction_differences  # noqa: E402


def test_count_prediction_differences_detects_changes():
    baseline = {
        "hits": {
            0.5: {"predictions": [(0.62, 1), (0.55, 0), (0.70, 1)]},
        }
    }
    adjusted = {
        "hits": {
            0.5: {"predictions": [(0.64, 1), (0.55, 0), (0.72, 1)]},
        }
    }
    changed, total = count_prediction_differences(baseline, adjusted)
    assert total == 3
    assert changed == 2
