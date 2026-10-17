"""
Walk-forward symmetric post-hoc calibration for NFL prop probabilities.

Only applies per-stat scaling when it improves out-of-sample Brier vs the raw model.
Symmetric form preserves P(over) + P(under) = 1 at the same line:
    p_cal = 0.5 + alpha * (p_raw - 0.5)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

DEFAULT_PARAMS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "nfl_isotonic_calibration.json"
)


class NFLPosthocCalibrator:
    def __init__(self, params_path: Optional[Path] = None):
        self.params_path = params_path or DEFAULT_PARAMS_PATH
        self._stats: Dict[str, Dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.params_path.exists():
            return
        try:
            raw = json.loads(self.params_path.read_text())
            self._stats = raw.get("stats", {})
        except (json.JSONDecodeError, OSError):
            self._stats = {}

    def is_enabled(self, stat_type: str) -> bool:
        entry = self._stats.get(stat_type)
        return bool(entry and entry.get("enabled"))

    def apply(self, stat_type: str, raw_prob: float) -> float:
        entry = self._stats.get(stat_type)
        if not entry or not entry.get("enabled"):
            return raw_prob
        alpha = float(entry.get("alpha", 1.0))
        p = 0.5 + alpha * (raw_prob - 0.5)
        return max(0.01, min(0.99, p))

    @staticmethod
    def fit_symmetric_alpha(
        pairs: list,
        min_samples: int = 200,
        grid: Optional[list] = None,
    ) -> Optional[Dict]:
        """Find alpha in (0,1] minimizing Brier; return None if no improvement vs alpha=1."""
        if not pairs or len(pairs) < min_samples:
            return None
        if grid is None:
            grid = [round(x, 2) for x in [1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5]]

        def brier(alpha: float) -> float:
            total = 0.0
            for p_raw, y in pairs:
                p = 0.5 + alpha * (p_raw - 0.5)
                p = max(0.01, min(0.99, p))
                total += (p - y) ** 2
            return total / len(pairs)

        brier_one = brier(1.0)
        best_alpha = 1.0
        best_brier = brier_one
        for alpha in grid:
            if alpha <= 0:
                continue
            b = brier(alpha)
            if b < best_brier - 1e-6:
                best_brier = b
                best_alpha = alpha

        if best_alpha >= 0.999 or best_brier >= brier_one - 1e-5:
            return {"enabled": False, "alpha": 1.0, "brier_raw": round(brier_one, 5), "brier_cal": round(brier_one, 5)}
        return {
            "enabled": True,
            "alpha": round(best_alpha, 3),
            "brier_raw": round(brier_one, 5),
            "brier_cal": round(best_brier, 5),
        }

    def save(self, stats_maps: Dict[str, Dict], meta: Optional[Dict] = None) -> None:
        payload = {"meta": meta or {}, "stats": stats_maps}
        self.params_path.parent.mkdir(parents=True, exist_ok=True)
        self.params_path.write_text(json.dumps(payload, indent=2))
        self._stats = stats_maps
