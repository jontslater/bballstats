"""
Walk-forward isotonic calibration for NFL prop probabilities.

Fits per-stat isotonic maps on out-of-sample backtest pairs and applies them
at inference time. Params are stored in data/nfl_isotonic_calibration.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from sklearn.isotonic import IsotonicRegression
except ImportError:  # pragma: no cover
    IsotonicRegression = None

DEFAULT_PARAMS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "nfl_isotonic_calibration.json"
)


class NFLPosthocCalibrator:
    def __init__(self, params_path: Optional[Path] = None):
        self.params_path = params_path or DEFAULT_PARAMS_PATH
        self._maps: Dict[str, Dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.params_path.exists():
            return
        try:
            raw = json.loads(self.params_path.read_text())
            self._maps = raw.get("stats", {})
        except (json.JSONDecodeError, OSError):
            self._maps = {}

    def apply(self, stat_type: str, raw_prob: float) -> float:
        if stat_type not in self._maps:
            return raw_prob
        entry = self._maps[stat_type]
        xs = entry.get("x", [])
        ys = entry.get("y", [])
        if len(xs) < 2:
            return raw_prob
        return float(np.interp(raw_prob, xs, ys))

    @staticmethod
    def fit_isotonic(pairs: List[Tuple[float, int]], min_samples: int = 200) -> Optional[Dict]:
        if not pairs or len(pairs) < min_samples or IsotonicRegression is None:
            return None
        preds = np.array([p for p, _ in pairs], dtype=float)
        outcomes = np.array([y for _, y in pairs], dtype=float)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99)
        iso.fit(preds, outcomes)
        # Store monotone knots for lightweight runtime apply
        x_grid = np.linspace(0.05, 0.95, 19)
        y_grid = iso.predict(x_grid)
        return {"x": [round(float(x), 4) for x in x_grid], "y": [round(float(y), 4) for y in y_grid]}

    def save(self, stats_maps: Dict[str, Dict], meta: Optional[Dict] = None) -> None:
        payload = {"meta": meta or {}, "stats": stats_maps}
        self.params_path.parent.mkdir(parents=True, exist_ok=True)
        self.params_path.write_text(json.dumps(payload, indent=2))
        self._maps = stats_maps
