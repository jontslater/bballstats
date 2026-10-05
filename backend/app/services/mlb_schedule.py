"""
Persist MLB Stats API schedule rows into GameSchedule and Game.

Predictions and suggested bets query the games table, not game_schedules.
mlb_collect_schedule previously wrote GameSchedule only, so upcoming
postseason games listed by the Stats API never became Game rows.
"""
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Game, GameSchedule, Team
from app.scrapers.mlb_api_client import MLB_TEAM_ID_TO_ABBREV


# Regular season plus every postseason series type the Stats API uses.
# Note: gameTypes=P is NOT an umbrella on statsapi.mlb.com (it returns 0 games);
# individual codes F/D/L/W are required. R = regular season.
MLB_INCLUDED_GAME_TYPES = {'R', 'F', 'D', 'L', 'W', 'P'}

MLB_STATUS_MAP = {
    'Final': 'finished',
    'Game Over': 'finished',
    'Completed Early': 'finished',
    'In Progress': 'in_progress',
    'Manager Challenge': 'in_progress',
    'Review': 'in_progress',
    'Delayed': 'in_progress',
    'Suspended': 'in_progress',
    'Postponed': 'postponed',
    'Cancelled': 'cancelled',
    'Canceled': 'cancelled',
}


def mlb_external_game_id(game_pk) -> Optional[str]:
    """Desktop backfill pattern: espn_game_id = MLB_<gamePk>."""
    if game_pk is None or game_pk == '':
        return None
    return f"MLB_{game_pk}"


def mlb_game_status(api_status: Optional[str]) -> str:
    if not api_status:
        return 'scheduled'
    return MLB_STATUS_MAP.get(api_status, 'scheduled')


def find_mlb_team(db: Session, abbrev: Optional[str]) -> Optional[Team]:
    if not abbrev:
        return None
    return db.query(Team).filter(Team.sport == 'MLB', Team.abbreviation == abbrev).first()


def _lookup_existing_game(db: Session, box_id: Optional[str], game_date: date, home_id: int, away_id: int) -> Optional[Game]:
    existing = None
    if box_id:
        existing = db.query(Game).filter(Game.sport == 'MLB', Game.espn_game_id == box_id).first()
    if not existing:
        existing = db.query(Game).filter(
            Game.sport == 'MLB',
            Game.game_date == game_date,
            Game.home_team_id == home_id,
            Game.away_team_id == away_id,
        ).first()
    return existing


def _lookup_existing_schedule(db: Session, box_id: Optional[str], game_date: date, home_id: int, away_id: int) -> Optional[GameSchedule]:
    existing = None
    if box_id:
        existing = db.query(GameSchedule).filter(
            GameSchedule.sport == 'MLB',
            GameSchedule.external_game_id == box_id,
        ).first()
        if not existing:
            existing = db.query(GameSchedule).filter(
                GameSchedule.sport == 'MLB',
                GameSchedule.nba_game_id == box_id,
            ).first()
    if not existing:
        existing = db.query(GameSchedule).filter(
            GameSchedule.sport == 'MLB',
            GameSchedule.game_date == game_date,
            GameSchedule.home_team_id == home_id,
            GameSchedule.away_team_id == away_id,
        ).first()
    return existing


def persist_mlb_schedule_games(db: Session, api_games: List[Dict], season) -> Dict[str, int]:
    """
    Upsert GameSchedule and Game rows from MLBAPIClient.get_schedule() dicts.

    Includes postseason series (gameType F/D/L/W/P) as well as regular season.
    Dedupes by MLB gamePk (espn_game_id/external_game_id = MLB_<gamePk>) and by
    date + home/away teams. Does not create a second row when the game already exists.
    """
    created_schedules = updated_schedules = 0
    created_games = updated_games = errors = 0
    skipped_type = 0

    for g in api_games:
        try:
            game_type = g.get('game_type')
            if game_type and game_type not in MLB_INCLUDED_GAME_TYPES:
                skipped_type += 1
                continue

            home_id = g.get('home_id')
            away_id = g.get('away_id')
            home_abbrev = MLB_TEAM_ID_TO_ABBREV.get(home_id) if home_id else None
            away_abbrev = MLB_TEAM_ID_TO_ABBREV.get(away_id) if away_id else None
            if not home_abbrev or not away_abbrev:
                errors += 1
                continue

            home_team = find_mlb_team(db, home_abbrev)
            away_team = find_mlb_team(db, away_abbrev)
            if not home_team or not away_team or home_team.team_id == away_team.team_id:
                errors += 1
                continue

            box_id = mlb_external_game_id(g.get('game_id'))
            raw_date = g.get('game_date')
            if isinstance(raw_date, date) and not isinstance(raw_date, datetime):
                game_date = raw_date
            else:
                game_date = datetime.strptime(str(raw_date), '%Y-%m-%d').date()

            status = mlb_game_status(g.get('status'))

            game = _lookup_existing_game(
                db, box_id, game_date, home_team.team_id, away_team.team_id
            )
            if game:
                if box_id and game.espn_game_id != box_id:
                    game.espn_game_id = box_id
                game.game_status = status
                game.game_date = game_date
                updated_games += 1
            else:
                game = Game(
                    sport='MLB',
                    game_date=game_date,
                    season_id=season.season_id,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    game_status=status,
                    espn_game_id=box_id,
                )
                db.add(game)
                db.flush()
                created_games += 1

            schedule = _lookup_existing_schedule(
                db, box_id, game_date, home_team.team_id, away_team.team_id
            )
            if schedule:
                if box_id:
                    if schedule.nba_game_id != box_id:
                        schedule.nba_game_id = box_id
                    if schedule.external_game_id != box_id:
                        schedule.external_game_id = box_id
                schedule.status = status
                schedule.game_date = game_date
                schedule.game_id = game.game_id
                updated_schedules += 1
            else:
                db.add(GameSchedule(
                    sport='MLB',
                    game_date=game_date,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    season_id=season.season_id,
                    nba_game_id=box_id,
                    external_game_id=box_id,
                    status=status,
                    game_id=game.game_id,
                ))
                created_schedules += 1
        except Exception:
            errors += 1
            continue

    return {
        'created_schedules': created_schedules,
        'updated_schedules': updated_schedules,
        'created_games': created_games,
        'updated_games': updated_games,
        'errors': errors,
        'skipped_type': skipped_type,
    }
