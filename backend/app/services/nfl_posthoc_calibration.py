"""
Walk-forward post-hoc calibration for NFL prop OVER probabilities.

- Symmetric scale: p = 0.5 + α(p_raw − 0.5)
- High-bucket (over-side) compression: p = knee + (p − knee) × factor for p > knee
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
        entry = self._stats.get(stat_type) or {}
        return bool(entry.get("enabled") or entry.get("high_enabled"))

    def apply(self, stat_type: str, raw_prob: float) -> float:
        entry = self._stats.get(stat_type)
        if not entry:
            return raw_prob
        p = float(raw_prob)
        if entry.get("enabled"):
            alpha = float(entry.get("alpha", 1.0))
            p = 0.5 + alpha * (p - 0.5)
        if entry.get("high_enabled"):
            knee = float(entry.get("high_knee", 0.55))
            factor = float(entry.get("high_factor", 0.7))
            if p > knee:
                p = knee + (p - knee) * factor
        return max(0.01, min(0.99, p))

    @staticmethod
    def _brier(pairs: List[Tuple[float, int]], transform) -> float:
        if not pairs:
            return 0.0
        total = 0.0
        for p_raw, y in pairs:
            p = max(0.01, min(0.99, transform(p_raw)))
            total += (p - y) ** 2
        return total / len(pairs)

    @staticmethod
    def fit_prop_calibration(
        train_pairs: List[Tuple[float, int]],
        val_pairs: List[Tuple[float, int]],
        min_train: int = 120,
        min_val: int = 80,
    ) -> Dict:
        """Fit α and high-bucket factor on train; enable only if val Brier beats raw."""
        if len(train_pairs) < min_train or len(val_pairs) < min_val:
            return {"enabled": False, "high_enabled": False, "alpha": 1.0}

        alphas = [1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7]
        knees = [0.52, 0.55, 0.58]
        factors = [0.45, 0.55, 0.65, 0.75, 0.85]

        def make_transform(alpha: float, high_knee: Optional[float], high_factor: Optional[float]):
            def _t(p_raw: float) -> float:
                p = 0.5 + alpha * (p_raw - 0.5)
                if high_knee is not None and high_factor is not None and p > high_knee:
                    p = high_knee + (p - high_knee) * high_factor
                return p

            return _t

        raw_val = NFLPosthocCalibrator._brier(val_pairs, lambda x: x)
        best = {"enabled": False, "high_enabled": False, "alpha": 1.0, "val_brier": raw_val}
        best_b = raw_val

        for alpha in alphas:
            for knee in knees:
                for factor in factors:
                    tr = make_transform(alpha, knee, factor)
                    vb = NFLPosthocCalibrator._brier(val_pairs, tr)
                    if vb < best_b - 0.0003:
                        best_b = vb
                        best = {
                            "enabled": alpha < 0.999,
                            "high_enabled": True,
                            "alpha": round(alpha, 3),
                            "high_knee": round(knee, 3),
                            "high_factor": round(factor, 3),
                            "brier_raw": round(raw_val, 5),
                            "brier_cal": round(vb, 5),
                            "val_brier": round(vb, 5),
                        }

        # Also try alpha-only and high-only
        for alpha in alphas:
            tr = make_transform(alpha, None, None)
            vb = NFLPosthocCalibrator._brier(val_pairs, tr)
            if vb < best_b - 0.0003:
                best_b = vb
                best = {
                    "enabled": alpha < 0.999,
                    "high_enabled": False,
                    "alpha": round(alpha, 3),
                    "brier_raw": round(raw_val, 5),
                    "brier_cal": round(vb, 5),
                    "val_brier": round(vb, 5),
                }

        if best_b >= raw_val - 0.0005:
            return {
                "enabled": False,
                "high_enabled": False,
                "alpha": 1.0,
                "brier_raw": round(raw_val, 5),
                "brier_cal": round(raw_val, 5),
                "val_brier": round(raw_val, 5),
            }
        return best

    def save(self, stats_maps: Dict[str, Dict], meta: Optional[Dict] = None) -> None:
        payload = {"meta": meta or {}, "stats": stats_maps}
        self.params_path.parent.mkdir(parents=True, exist_ok=True)
        self.params_path.write_text(json.dumps(payload, indent=2))
        self._stats = stats_maps
