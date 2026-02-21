#!/usr/bin/env python3
"""
Collect and store MLB game schedules from MLB Stats API.

Uses official MLB Stats API - no rate limits (unlike Baseball Reference).
Usage:
    python scripts/mlb_collect_schedule.py [--season SEASON] [--start-date DATE] [--end-date DATE]
    python scripts/mlb_collect_schedule.py --days 7  # Collect next 7 days
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime, date, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.models import GameSchedule, Team, Season
from app.scrapers.mlb_api_client import MLBAPIClient, MLB_TEAM_ID_TO_ABBREV


def find_team_by_abbrev(db, abbrev: str):
    """Find MLB team by abbreviation."""
    return db.query(Team).filter(
        Team.sport == 'MLB',
        Team.abbreviation == abbrev
    ).first()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=str, help='Season year (e.g., 2024)')
    parser.add_argument('--start-date', type=str, help='Start date YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, help='End date YYYY-MM-DD')
    parser.add_argument('--days', type=int, default=30, help='Number of days to collect')
    args = parser.parse_args()

    db = SessionLocal()
    client = MLBAPIClient(delay=0.5)

    try:
        season_year = args.season or str(date.today().year)
        season = db.query(Season).filter(
            Season.sport == 'MLB',
            Season.season_year == season_year
        ).first()
        if not season:
            print(f"Season {season_year} not found. Run seed_mlb_teams.py first.")
            return

        if args.start_date:
            start = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        else:
            start = date.today()
        if args.end_date:
            end = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        else:
            end = start + timedelta(days=args.days)

        print(f"Collecting MLB schedule from {start} to {end} (MLB Stats API)...")
        total_c, total_u, total_e = 0, 0, 0

        current = start
        while current <= end:
            games = client.get_schedule(game_date=current)
            for g in games:
                try:
                    home_id = g.get('home_id')
                    away_id = g.get('away_id')
                    home_abbrev = client.get_team_abbrev(home_id) if home_id else None
                    away_abbrev = client.get_team_abbrev(away_id) if away_id else None

                    if not home_abbrev or not away_abbrev:
                        total_e += 1
                        continue

                    home_team = find_team_by_abbrev(db, home_abbrev)
                    away_team = find_team_by_abbrev(db, away_abbrev)
                    if not home_team or not away_team:
                        total_e += 1
                        continue
                    if home_team.team_id == away_team.team_id:
                        total_e += 1
                        continue

                    game_id = g.get('game_id')
                    box_id = f"MLB_{game_id}" if game_id else None
                    game_date = datetime.strptime(g.get('game_date', str(current)), '%Y-%m-%d').date()

                    existing = db.query(GameSchedule).filter(
                        GameSchedule.sport == 'MLB',
                        GameSchedule.game_date == game_date,
                        GameSchedule.home_team_id == home_team.team_id,
                        GameSchedule.away_team_id == away_team.team_id
                    ).first()
                    if not existing and box_id:
                        existing = db.query(GameSchedule).filter(
                            GameSchedule.sport == 'MLB',
                            GameSchedule.nba_game_id == box_id
                        ).first()

                    status_map = {'Final': 'finished', 'Game Over': 'finished', 'In Progress': 'in_progress'}
                    status = status_map.get(g.get('status', ''), 'scheduled')

                    if existing:
                        if box_id and (not existing.nba_game_id or existing.nba_game_id != box_id):
                            existing.nba_game_id = box_id
                        existing.status = status
                        total_u += 1
                    else:
                        db.add(GameSchedule(
                            sport='MLB',
                            game_date=game_date,
                            home_team_id=home_team.team_id,
                            away_team_id=away_team.team_id,
                            season_id=season.season_id,
                            nba_game_id=box_id,
                            status=status
                        ))
                        total_c += 1
                except Exception as e:
                    total_e += 1
                    continue

            db.commit()
            current += timedelta(days=1)

        print(f"Created: {total_c}, Updated: {total_u}, Errors: {total_e}")
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
