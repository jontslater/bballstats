#!/usr/bin/env python3
"""
Out-of-sample NBA prop calibration (2025-26 fit through Feb, test Mar-end).

Usage:
    python scripts/nba_calibration_check.py
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.nba_prop_calibration import refresh_prop_gate_cache


def print_tables(reports):
    print("=" * 80)
    print("NBA PROP CALIBRATION (out-of-sample)")
    print("=" * 80)
    for stat, rep in reports.items():
        print(f"\n## {stat}")
        print(f"Brier score: {rep.brier:.4f}")
        print(f"Median-line P(over) in 0.45-0.55 band: {rep.median_line_p_over:.3f}")
        print(f"Passes gate: {rep.passes_gate}")
        print(f"{'Bucket':<8} | {'n':>5} | {'pred':>7} | {'actual':>7}")
        for label in ("50-54", "55-59", "60-64", "65-69", "70+"):
            b = rep.buckets.get(label, {})
            n = int(b.get("n", 0))
            if n == 0:
                print(f"{label:<8} | {0:5} | {'-':>7} | {'-':>7}")
            else:
                print(
                    f"{label:<8} | {n:5} | {b.get('predicted', 0)*100:6.1f}% | {b.get('actual', 0)*100:6.1f}%"
                )


def main():
    db = SessionLocal()
    try:
        reports = refresh_prop_gate_cache(db)
        print_tables(reports)
    finally:
        db.close()


if __name__ == "__main__":
    main()
