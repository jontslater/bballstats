#!/usr/bin/env python3
"""One-off migration: dedupe NBA predictions (run after deploy)."""
import sys
from pathlib import Path

backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend.parent))
sys.path.insert(0, str(backend))

from app.database import SessionLocal
from app.services.nba_prediction_cleanup import dedupe_nba_predictions


def main() -> int:
    db = SessionLocal()
    try:
        print(dedupe_nba_predictions(db, dry_run=False))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
