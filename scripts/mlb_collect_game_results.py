#!/usr/bin/env python3
"""
Collect MLB game results and box scores from MLB Stats API.

Uses official MLB Stats API - no rate limits (unlike Baseball Reference).
Usage:
    python scripts/mlb_collect_game_results.py [--date DATE]
    python scripts/mlb_collect_game_results.py --previous-day
    python scripts/mlb_collect_game_results.py --season 2025 --days 90
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime, date, timedelta
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import SessionLocal
from app.models import Game, Team, Season, Player, PlayerGameStat
from app.scrapers.mlb_api_client import MLBAPIClient


def find_team_by_abbrev(db: Session, abbrev: str):
    return db.query(Team).filter(
        Team.sport == 'MLB',
        Team.abbreviation == abbrev
    ).first()


def get_or_create_mlb_player(db: Session, player_name: str, team: Team, position: str = None, is_batter: bool = False, is_pitcher: bool = False):
    """
    Get or create MLB player by name and team.
    
    Args:
        player_name: Player name
        team: Team object
        position: Specific position (e.g., 'C', 'P', 'OF')
        is_batter: True if player has batting stats
        is_pitcher: True if player has pitching stats
    """
    player = db.query(Player).filter(
        Player.sport == 'MLB',
        Player.name == player_name
    ).first()
    
    if not player:
        # Determine position based on role if not provided
        if not position:
            if is_pitcher:
                position = 'P'
            elif is_batter:
                position = 'DH'  # Default for batters without specific position
            else:
                position = 'P'  # Default fallback
        
        player = Player(
            sport='MLB',
            name=player_name,
            position=position,
            current_team_id=team.team_id
        )
        db.add(player)
        db.flush()
    else:
        # Update team if changed
        if player.current_team_id != team.team_id:
            player.current_team_id = team.team_id
        
        # Update position if we have better information
        if position and player.position == 'P' and is_batter and not is_pitcher:
            # Player was defaulted to P but is actually a batter
            player.position = position if position != 'P' else 'DH'
    
    return player


def date_has_stats(db: Session, game_date: date) -> bool:
    count = db.query(func.count(PlayerGameStat.stat_id)).join(
        Game, PlayerGameStat.game_id == Game.game_id
    ).filter(
        PlayerGameStat.sport == 'MLB',
        Game.sport == 'MLB',
        Game.game_date == game_date
    ).scalar()
    return (count or 0) > 0


def collect_games_for_date(
    db: Session,
    client: MLBAPIClient,
    game_date: date,
    skip_if_has_stats: bool = False
):
    season = db.query(Season).filter(
        Season.sport == 'MLB',
        Season.season_year == str(game_date.year)
    ).first()
    if not season:
        season = db.query(Season).filter(Season.sport == 'MLB').order_by(Season.season_id.desc()).first()
    if not season:
        print("No MLB season found. Run seed_mlb_teams.py first.")
        return 0, 0

    if skip_if_has_stats and date_has_stats(db, game_date):
        return 0, 0

    games = client.get_schedule(game_date=game_date)
    games = [g for g in games if g.get('status') in ('Final', 'Game Over')]
    if not games:
        return 0, 0

    games_created = games_processed = 0
    for g in games:
        try:
            home_id = g.get('home_id')
            away_id = g.get('away_id')
            home_abbrev = client.get_team_abbrev(home_id) if home_id else None
            away_abbrev = client.get_team_abbrev(away_id) if away_id else None

            if not home_abbrev or not away_abbrev:
                continue

            home_team = find_team_by_abbrev(db, home_abbrev)
            away_team = find_team_by_abbrev(db, away_abbrev)
            if not home_team or not away_team:
                continue
            if home_team.team_id == away_team.team_id:
                continue

            game_id = g.get('game_id')
            box_data = client.get_box_score_data(game_id)
            if not box_data:
                continue

            parsed = client.parse_box_score_for_db(box_data, home_abbrev, away_abbrev)
            away_score = parsed.get('away_score') or g.get('away_score')
            home_score = parsed.get('home_score') or g.get('home_score')
            if away_score is not None:
                try:
                    away_score = int(away_score)
                except (ValueError, TypeError):
                    away_score = None
            if home_score is not None:
                try:
                    home_score = int(home_score)
                except (ValueError, TypeError):
                    home_score = None

            game_date_obj = datetime.strptime(g.get('game_date', str(game_date)), '%Y-%m-%d').date()

            existing = db.query(Game).filter(
                Game.sport == 'MLB',
                Game.game_date == game_date_obj,
                Game.home_team_id == home_team.team_id,
                Game.away_team_id == away_team.team_id
            ).first()

            if existing:
                game = existing
                if away_score is not None:
                    game.away_score = away_score
                if home_score is not None:
                    game.home_score = home_score
                game.game_status = 'finished'
            else:
                game = Game(
                    sport='MLB',
                    game_date=game_date_obj,
                    season_id=season.season_id,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    home_score=home_score,
                    away_score=away_score,
                    game_status='finished'
                )
                db.add(game)
                db.flush()
                games_created += 1

            for ps in parsed.get('player_stats', []):
                try:
                    with db.begin_nested():  # savepoint - rollback only this player on error
                        team_abbr = ps.get('team_abbreviation')
                        team = find_team_by_abbrev(db, team_abbr) if team_abbr else None
                        if not team:
                            continue
                        opponent = away_team if team.team_id == home_team.team_id else home_team
                        
                        # Get or create player with proper position based on role
                        is_batter = ps.get('is_batter', False)
                        is_pitcher = ps.get('is_pitcher', False)
                        position = ps.get('position')  # May be None
                        player = get_or_create_mlb_player(
                            db, ps['player_name'], team, 
                            position=position, 
                            is_batter=is_batter, 
                            is_pitcher=is_pitcher
                        )

                        existing_stat = db.query(PlayerGameStat).filter(
                            PlayerGameStat.sport == 'MLB',
                            PlayerGameStat.player_id == player.player_id,
                            PlayerGameStat.game_id == game.game_id
                        ).first()

                        if existing_stat:
                            stat = existing_stat
                        else:
                            stat = PlayerGameStat(
                                sport='MLB',
                                player_id=player.player_id,
                                game_id=game.game_id,
                                team_id=team.team_id,
                                opponent_team_id=opponent.team_id,
                                is_home=(team.team_id == home_team.team_id)
                            )
                            db.add(stat)
                            db.flush()

                        if ps.get('is_batter'):
                            stat.at_bats = ps.get('at_bats')
                            stat.plate_appearances = ps.get('plate_appearances')
                            stat.hits = ps.get('hits')
                            stat.doubles = ps.get('doubles')
                            stat.triples = ps.get('triples')
                            stat.home_runs = ps.get('home_runs')
                            stat.total_bases = ps.get('total_bases')
                            stat.rbis = ps.get('rbis')
                        if ps.get('is_pitcher'):
                            stat.innings_pitched = ps.get('innings_pitched')
                            stat.strikeouts = ps.get('strikeouts')
                            stat.hits_allowed = ps.get('hits_allowed')
                            stat.walks_allowed = ps.get('walks_allowed')
                except Exception as e:
                    # savepoint auto-rollback; skip this player, keep game intact
                    continue

            db.commit()
            games_processed += 1
        except Exception as e:
            db.rollback()
            print(f"Error: {e}")
            continue

    return games_created, games_processed


def collect_season_games(
    season_year: str = None,
    start_date: date = None,
    end_date: date = None,
    days_back: int = None,
    skip_existing: bool = False
):
    """Collect MLB game results for a date range. Uses MLB API - fast, no rate limits."""
    print("⚾ Collecting MLB Historical Game Results (MLB Stats API)...")
    print("=" * 60)

    db = SessionLocal()
    client = MLBAPIClient(delay=0.3)

    try:
        season = None
        if season_year:
            season = db.query(Season).filter(
                Season.sport == 'MLB',
                Season.season_year == str(season_year)
            ).first()

        if season and not start_date:
            start_date = season.start_date
        # If season has no start_date (seed doesn't set it), use MLB calendar defaults
        if not start_date and season_year:
            y = int(season_year)
            start_date = date(y, 3, 15)  # Spring training / opening day
        if not start_date:
            start_date = date.today() - timedelta(days=90)

        if end_date is None:
            if days_back:
                end_date = date.today() - timedelta(days=1)
                start_date = end_date - timedelta(days=days_back)
            else:
                # Use season end_date if set, else MLB default (Oct 31) or yesterday
                if season and season.end_date:
                    end_date = season.end_date
                elif season_year:
                    y = int(season_year)
                    end_date = date(y, 10, 31)  # Regular season + playoffs
                else:
                    end_date = date.today() - timedelta(days=1)

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        total_days = (end_date - start_date).days + 1
        print(f"Date range: {start_date} to {end_date} ({total_days} days)")
        if skip_existing:
            print("Skipping dates that already have stats")
        print()

        total_created = total_processed = 0
        current = start_date
        day_num = 0

        while current <= end_date:
            day_num += 1
            c, p = collect_games_for_date(db, client, current, skip_if_has_stats=skip_existing)
            total_created += c
            total_processed += p
            if p > 0 or c > 0:
                print(f"  [{day_num}/{total_days}] {current}: {c} created, {p} processed")

            current += timedelta(days=1)

        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"✅ Games created: {total_created}")
        print(f"✅ Games processed: {total_processed}")
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description='Collect MLB game results from MLB Stats API')
    parser.add_argument('--date', type=str, help='Single date YYYY-MM-DD')
    parser.add_argument('--previous-day', action='store_true')
    parser.add_argument('--season', type=str, help='Season year (e.g., 2025)')
    parser.add_argument('--start-date', type=str, help='Start date YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, help='End date YYYY-MM-DD')
    parser.add_argument('--days', type=int, help='Number of days to collect')
    parser.add_argument('--skip-existing', action='store_true', help='Skip dates with stats')
    args = parser.parse_args()

    if args.previous_day:
        game_date = date.today() - timedelta(days=1)
        db = SessionLocal()
        client = MLBAPIClient(delay=0.3)
        try:
            c, p = collect_games_for_date(db, client, game_date)
            print(f"Created {c} games, processed {p} games")
        finally:
            db.close()
        return

    if args.date and not (args.start_date or args.end_date or args.days):
        game_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        db = SessionLocal()
        client = MLBAPIClient(delay=0.3)
        try:
            c, p = collect_games_for_date(db, client, game_date)
            print(f"Created {c} games, processed {p} games")
        finally:
            db.close()
        return

    start = datetime.strptime(args.start_date, '%Y-%m-%d').date() if args.start_date else None
    end = datetime.strptime(args.end_date, '%Y-%m-%d').date() if args.end_date else None

    collect_season_games(
        season_year=args.season,
        start_date=start,
        end_date=end,
        days_back=args.days,
        skip_existing=args.skip_existing
    )


if __name__ == "__main__":
    main()
