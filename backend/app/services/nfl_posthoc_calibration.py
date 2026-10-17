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

    @staticmethod
    def fit_symmetric_alpha_holdout(
        pairs: list,
        min_samples: int = 200,
        holdout_frac: float = 0.25,
        grid: Optional[list] = None,
    ) -> Optional[Dict]:
        """Fit alpha on train split; enable only if holdout Brier improves vs raw."""
        if not pairs or len(pairs) < min_samples:
            return None
        if grid is None:
            grid = [round(x, 2) for x in [1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5]]

        split = max(int(len(pairs) * (1.0 - holdout_frac)), min_samples // 2)
        train = pairs[:split]
        test = pairs[split:]
        if len(test) < 80:
            test = pairs[-max(80, len(pairs) // 5) :]
            train = pairs[: len(pairs) - len(test)]

        def brier_on(pr: list, alpha: float) -> float:
            total = 0.0
            for p_raw, y in pr:
                p = max(0.01, min(0.99, 0.5 + alpha * (p_raw - 0.5)))
                total += (p - y) ** 2
            return total / len(pr)

        def best_alpha_for(pr: list) -> float:
            best_a = 1.0
            best_b = brier_on(pr, 1.0)
            for alpha in grid:
                if alpha <= 0:
                    continue
                b = brier_on(pr, alpha)
                if b < best_b - 1e-6:
                    best_b = b
                    best_a = alpha
            return best_a

        alpha = best_alpha_for(train)
        raw_test = brier_on(test, 1.0)
        cal_test = brier_on(test, alpha)
        raw_all = brier_on(pairs, 1.0)

        cal_all = brier_on(pairs, alpha)
        if cal_test >= raw_test - 0.001 or cal_all >= raw_all - 0.001:
            return {
                "enabled": False,
                "alpha": 1.0,
                "brier_raw": round(raw_all, 5),
                "brier_cal": round(raw_all, 5),
                "holdout_raw": round(raw_test, 5),
                "holdout_cal": round(cal_test, 5),
            }
        return {
            "enabled": True,
            "alpha": round(alpha, 3),
            "brier_raw": round(raw_all, 5),
            "brier_cal": round(cal_all, 5),
            "holdout_raw": round(raw_test, 5),
            "holdout_cal": round(cal_test, 5),
        }

    def save(self, stats_maps: Dict[str, Dict], meta: Optional[Dict] = None) -> None:
        payload = {"meta": meta or {}, "stats": stats_maps}
        self.params_path.parent.mkdir(parents=True, exist_ok=True)
        self.params_path.write_text(json.dumps(payload, indent=2))
        self._stats = stats_maps
