"""
Persist MLB Stats API schedule rows into GameSchedule and Game.

Predictions and suggested bets query the games table, not game_schedules.
mlb_collect_schedule previously wrote GameSchedule only, so upcoming
postseason games listed by the Stats API never became Game rows.

Schedule sync must also reconcile a lookback window: when MLB drops
if-necessary games (series clinched) or lists them as Unknown/Cancelled,
those Game rows stay `scheduled` forever unless we cancel them.
"""
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Game, GameSchedule, Team
from app.scrapers.mlb_api_client import MLB_TEAM_ID_TO_ABBREV


# Regular season plus every postseason series type the Stats API uses.
# Note: gameTypes=P is NOT an umbrella on statsapi.mlb.com (it returns 0 games);
# individual codes F/D/L/W are required. R = regular season.
MLB_INCLUDED_GAME_TYPES = {'R', 'F', 'D', 'L', 'W', 'P'}

# Daily sync looks this far back so a missed morning run still heals.
MLB_SCHEDULE_LOOKBACK_DAYS = 7

MLB_STATUS_MAP = {
    'Final': 'finished',
    'Game Over': 'finished',
    'Completed Early': 'finished',
    'In Progress': 'in_progress',
    'Manager Challenge': 'in_progress',
    'Review': 'in_progress',
    'Delayed': 'in_progress',
    'Suspended': 'in_progress',
    'Warmup': 'scheduled',
    'Pre-Game': 'scheduled',
    'Scheduled': 'scheduled',
    'Preview': 'scheduled',
    'Postponed': 'cancelled',  # non-playable; same gamePk can revive if rescheduled
    'Cancelled': 'cancelled',
    'Canceled': 'cancelled',
    'Unknown': 'cancelled',  # series-clinched if-necessary / dropped by Stats API
}

# DB statuses that may be voided when the API drops the game.
MLB_CANCELABLE_DB_STATUSES = ('scheduled', 'in_progress', 'postponed')
MLB_PROTECTED_DB_STATUSES = ('finished',)


def mlb_external_game_id(game_pk) -> Optional[str]:
    """Desktop backfill pattern: espn_game_id = MLB_<gamePk>."""
    if game_pk is None or game_pk == '':
        return None
    return f"MLB_{game_pk}"


def mlb_game_status(api_status: Optional[str]) -> str:
    if not api_status:
        return 'scheduled'
    mapped = MLB_STATUS_MAP.get(api_status)
    if mapped:
        return mapped
    # Status codes like 'Other' / unknown detailedState are not bettable.
    lowered = str(api_status).strip().lower()
    if lowered in ('unknown', 'cancelled', 'canceled', 'postponed', 'other'):
        return 'cancelled'
    return 'scheduled'


def is_non_playable_api_status(api_status: Optional[str]) -> bool:
    return mlb_game_status(api_status) == 'cancelled'


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


def _parse_api_game_date(raw_date, fallback: Optional[date] = None) -> Optional[date]:
    if isinstance(raw_date, date) and not isinstance(raw_date, datetime):
        return raw_date
    if raw_date:
        try:
            return datetime.strptime(str(raw_date)[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    return fallback


def _is_protected_historical_game(game: Game) -> bool:
    """Never void a finished game or one that already has scores."""
    if game.game_status in MLB_PROTECTED_DB_STATUSES:
        return True
    if game.home_score is not None or game.away_score is not None:
        return True
    return False


def _cancel_game_and_schedules(db: Session, game: Game) -> None:
    game.game_status = 'cancelled'
    q = db.query(GameSchedule).filter(GameSchedule.sport == 'MLB')
    if game.espn_game_id:
        schedules = q.filter(
            or_(
                GameSchedule.game_id == game.game_id,
                GameSchedule.external_game_id == game.espn_game_id,
                GameSchedule.nba_game_id == game.espn_game_id,
            )
        ).all()
    else:
        schedules = q.filter(GameSchedule.game_id == game.game_id).all()
    for schedule in schedules:
        schedule.status = 'cancelled'
        if schedule.game_id is None:
            schedule.game_id = game.game_id


def persist_mlb_schedule_games(db: Session, api_games: List[Dict], season) -> Dict[str, int]:
    """
    Upsert GameSchedule and Game rows from MLBAPIClient.get_schedule() dicts.

    Includes postseason series (gameType F/D/L/W/P) as well as regular season.
    Dedupes by MLB gamePk (espn_game_id/external_game_id = MLB_<gamePk>) and by
    date + home/away teams. Does not create a second row when the game already exists.

    Finished games are not downgraded. Unknown/Cancelled/Postponed API statuses
    map to cancelled so they drop out of suggested bets.
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
            game_date = _parse_api_game_date(g.get('game_date'))
            if not game_date:
                errors += 1
                continue

            status = mlb_game_status(g.get('status'))

            game = _lookup_existing_game(
                db, box_id, game_date, home_team.team_id, away_team.team_id
            )
            if game:
                if box_id and game.espn_game_id != box_id:
                    game.espn_game_id = box_id
                if not _is_protected_historical_game(game):
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
                if game.game_status == 'finished':
                    schedule.status = 'finished'
                else:
                    schedule.status = status
                schedule.game_date = game.game_date
                schedule.game_id = game.game_id
                updated_schedules += 1
            else:
                db.add(GameSchedule(
                    sport='MLB',
                    game_date=game.game_date,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    season_id=season.season_id,
                    nba_game_id=box_id,
                    external_game_id=box_id,
                    status=game.game_status if game.game_status == 'finished' else status,
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


def listed_mlb_box_ids(api_games: Iterable[Dict]) -> Set[str]:
    ids: Set[str] = set()
    for g in api_games:
        box_id = mlb_external_game_id(g.get('game_id'))
        if box_id:
            ids.add(box_id)
    return ids


def reconcile_mlb_schedule_window(
    db: Session,
    api_games: List[Dict],
    start: date,
    end: date,
) -> Dict[str, int]:
    """
    Cancel MLB Game/GameSchedule rows in [start, end] that the Stats API no
    longer lists (or that persist already mapped to cancelled).

    Does not delete rows and does not touch finished games or games with scores.
    """
    seen = listed_mlb_box_ids(api_games)
    games = db.query(Game).filter(
        Game.sport == 'MLB',
        Game.game_date >= start,
        Game.game_date <= end,
        Game.game_status.in_(MLB_CANCELABLE_DB_STATUSES),
    ).all()

    cancelled_games = 0
    for game in games:
        if _is_protected_historical_game(game):
            continue
        if game.espn_game_id and game.espn_game_id in seen:
            # Listed games were already upserted (including Unknown -> cancelled).
            continue
        _cancel_game_and_schedules(db, game)
        cancelled_games += 1

    # Schedules in the window with no Game row (or unlinked) still need voiding
    # if their external id disappeared from the API.
    cancelled_schedules = 0
    schedules = db.query(GameSchedule).filter(
        GameSchedule.sport == 'MLB',
        GameSchedule.game_date >= start,
        GameSchedule.game_date <= end,
        GameSchedule.status.in_(MLB_CANCELABLE_DB_STATUSES),
    ).all()
    for schedule in schedules:
        ext = schedule.external_game_id or schedule.nba_game_id
        if ext and ext in seen:
            continue
        if schedule.game_id:
            game = db.query(Game).filter(Game.game_id == schedule.game_id).first()
            if game and _is_protected_historical_game(game):
                continue
        schedule.status = 'cancelled'
        cancelled_schedules += 1

    return {
        'cancelled_games': cancelled_games,
        'cancelled_schedules': cancelled_schedules,
        'seen_games': len(seen),
    }
