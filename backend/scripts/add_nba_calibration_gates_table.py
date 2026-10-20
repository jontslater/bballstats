#!/usr/bin/env python3
"""Create nba_prop_calibration_gates table."""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy import inspect

from app.database import Base, engine
from app.models.nba_prop_calibration_gate import NbaPropCalibrationGate


def main():
    insp = inspect(engine)
    if insp.has_table("nba_prop_calibration_gates"):
        print("nba_prop_calibration_gates already exists")
        return
    NbaPropCalibrationGate.__table__.create(engine)
    print("Created nba_prop_calibration_gates")


if __name__ == "__main__":
    main()
