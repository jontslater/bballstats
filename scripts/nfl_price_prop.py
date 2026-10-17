#!/usr/bin/env python3
"""
Price an NFL player prop vs a sportsbook line (FanDuel / The Odds API markets).

Usage:
  PYTHONUTF8=1 python scripts/nfl_price_prop.py --player "Patrick Mahomes" --market player_pass_completions --line 17.5 --odds -115
  PYTHONUTF8=1 python scripts/nfl_price_prop.py --player "Josh Allen" --stat attempts --line 22.5 --odds +100 --team BUF
"""
import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.nfl_prop_pricing import NFLPropPricingService


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--player", required=True)
    p.add_argument("--line", type=float, required=True)
    p.add_argument("--odds", type=str, help="American odds")
    p.add_argument("--stat", type=str, help="Internal stat_type")
    p.add_argument("--market", type=str, help="The Odds API market key")
    p.add_argument("--team", type=str, help="Team abbrev")
    p.add_argument("--game-id", type=int)
    args = p.parse_args()

    stat = args.market or args.stat
    if not stat:
        p.error("Provide --stat or --market")

    db = SessionLocal()
    try:
        svc = NFLPropPricingService(db)
        out = svc.price_prop(
            player_name=args.player,
            stat_type=stat,
            line=args.line,
            sportsbook_odds=args.odds,
            game_id=args.game_id,
            team_abbrev=args.team,
        )
        print(json.dumps({
            "player_name": out.player_name,
            "stat_type": out.stat_type,
            "line": out.line,
            "calibrated_probability": out.calibrated_probability,
            "raw_model_probability": out.model_probability,
            "break_even_american_odds": out.break_even_american_odds,
            "sportsbook_american_odds": out.sportsbook_american_odds,
            "implied_probability": out.implied_probability,
            "edge": out.edge,
            "sample_size": out.sample_size,
            "player_mean": out.player_mean,
        }, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
