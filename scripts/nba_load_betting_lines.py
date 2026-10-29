#!/usr/bin/env python3
"""
Load FanDuel (with DraftKings fallback) NBA player prop lines from The Odds API.

Requires ODDS_API_KEY in the environment. Responses are cached under data/cache/odds_api/.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.scrapers.odds_api_client import OddsApiClient
from app.services.nba_odds_lines import (
    central_today,
    ingest_nba_player_prop_lines,
    parse_markets_arg,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest NBA player prop lines from The Odds API")
    parser.add_argument(
        "--date",
        type=str,
        help="Game date in US Central (YYYY-MM-DD). Defaults to today in Central.",
    )
    parser.add_argument(
        "--markets",
        type=str,
        help="Comma-separated Odds API markets (default: player_points,player_rebounds,...)",
    )
    parser.add_argument(
        "--predictions-only",
        action="store_true",
        help="Only fetch odds for games that already have model predictions (saves API credits).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log matched lines without writing to the database.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not read or write on-disk API response cache.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cached API responses (still writes fresh cache unless --no-cache).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ODDS_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        logger.error("ODDS_API_KEY is not set.")
        return 1

    try:
        markets = parse_markets_arg(args.markets)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    target_date = date.fromisoformat(args.date) if args.date else central_today()

    client = OddsApiClient(
        api_key or "dry-run-placeholder",
        use_cache=not args.no_cache,
        force_refresh=args.refresh,
    )
    db = SessionLocal()
    try:
        summary = ingest_nba_player_prop_lines(
            db,
            client,
            target_date,
            markets,
            dry_run=args.dry_run,
            predictions_only=args.predictions_only,
        )
        logger.info(
            "Done date=%s events=%s fetched=%s upserted=%s dry_run=%s remaining=%s",
            target_date,
            summary.events_considered,
            summary.events_fetched,
            summary.lines_upserted,
            summary.lines_dry_run,
            client.last_requests_remaining,
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
