#!/usr/bin/env python3
"""Remove duplicate NBA prediction rows (keep one per player/game/stat)."""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.nba_prediction_cleanup import dedupe_nba_predictions


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Dedupe NBA prediction rows")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = dedupe_nba_predictions(db, dry_run=args.dry_run)
        print(result)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
