"""
Persist ESPN NBA schedule rows into GameSchedule and Game.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models import Game, GameSchedule, Season, Team
from app.scrapers.espn_nba_client import normalize_nba_abbrev

NBA_SCHEDULE_LOOKBACK_DAYS = 7


def find_nba_team(db: Session, abbrev: Optional[str]) -> Optional[Team]:
    if not abbrev:
        return None
    abbrev = normalize_nba_abbrev(abbrev)
    return db.query(Team).filter(Team.sport == "NBA", Team.abbreviation == abbrev).first()


def nba_game_status(api_status: str) -> str:
    if api_status in ("finished", "in_progress", "scheduled", "cancelled"):
        return api_status
    return "scheduled"


def _lookup_game(db: Session, espn_id: Optional[str], game_date: date, home_id: int, away_id: int) -> Optional[Game]:
    if espn_id:
        existing = db.query(Game).filter(Game.sport == "NBA", Game.espn_game_id == espn_id).first()
        if existing:
            return existing
    return (
        db.query(Game)
        .filter(
            Game.sport == "NBA",
            Game.game_date == game_date,
            Game.home_team_id == home_id,
            Game.away_team_id == away_id,
        )
        .first()
    )


def _lookup_schedule(
    db: Session, espn_id: Optional[str], game_date: date, home_id: int, away_id: int
) -> Optional[GameSchedule]:
    if espn_id:
        existing = db.query(GameSchedule).filter(
            GameSchedule.sport == "NBA",
            GameSchedule.external_game_id == espn_id,
        ).first()
        if existing:
            return existing
        existing = db.query(GameSchedule).filter(
            GameSchedule.sport == "NBA",
            GameSchedule.nba_game_id == espn_id,
        ).first()
        if existing:
            return existing
    return (
        db.query(GameSchedule)
        .filter(
            GameSchedule.sport == "NBA",
            GameSchedule.game_date == game_date,
            GameSchedule.home_team_id == home_id,
            GameSchedule.away_team_id == away_id,
        )
        .first()
    )


def persist_nba_schedule_games(db: Session, games: List[Dict], season: Season) -> Dict[str, int]:
    created_games = updated_games = created_schedules = updated_schedules = errors = 0

    for g in games:
        try:
            home = find_nba_team(db, g.get("home_team"))
            away = find_nba_team(db, g.get("away_team"))
            if not home or not away:
                errors += 1
                continue

            espn_id = str(g.get("espn_game_id", "")) or None
            game_date = g["game_date"]
            status = nba_game_status(g.get("status", "scheduled"))

            sched = _lookup_schedule(db, espn_id, game_date, home.team_id, away.team_id)
            if g.get("game_time"):
                gt = g["game_time"]
            else:
                gt = None
            if sched:
                sched.status = status
                if espn_id:
                    sched.external_game_id = espn_id
                    sched.nba_game_id = espn_id
                if gt:
                    sched.game_time = gt
                updated_schedules += 1
            else:
                sched = GameSchedule(
                    sport="NBA",
                    season_id=season.season_id,
                    game_date=game_date,
                    game_time=gt,
                    home_team_id=home.team_id,
                    away_team_id=away.team_id,
                    status=status,
                    external_game_id=espn_id,
                    nba_game_id=espn_id,
                )
                db.add(sched)
                created_schedules += 1
                db.flush()

            game = _lookup_game(db, espn_id, game_date, home.team_id, away.team_id)
            if game:
                game.game_status = status
                if espn_id and not game.espn_game_id:
                    game.espn_game_id = espn_id
                if g.get("home_score") is not None:
                    game.home_score = g.get("home_score")
                if g.get("away_score") is not None:
                    game.away_score = g.get("away_score")
                sched.game_id = game.game_id
                updated_games += 1
            else:
                game = Game(
                    sport="NBA",
                    game_date=game_date,
                    season_id=season.season_id,
                    home_team_id=home.team_id,
                    away_team_id=away.team_id,
                    home_score=g.get("home_score"),
                    away_score=g.get("away_score"),
                    game_status=status,
                    espn_game_id=espn_id,
                )
                db.add(game)
                db.flush()
                sched.game_id = game.game_id
                created_games += 1
        except Exception:
            errors += 1

    return {
        "created_games": created_games,
        "updated_games": updated_games,
        "created_schedules": created_schedules,
        "updated_schedules": updated_schedules,
        "errors": errors,
    }


def reconcile_nba_schedule_window(
    db: Session, api_games: List[Dict], window_start: date, window_end: date
) -> Dict[str, int]:
    """Cancel NBA games in window that disappeared from ESPN scoreboard (postponed)."""
    api_ids: Set[str] = {str(g["espn_game_id"]) for g in api_games if g.get("espn_game_id")}
    cancelled_games = cancelled_schedules = 0

    stale_games = (
        db.query(Game)
        .filter(
            Game.sport == "NBA",
            Game.game_date >= window_start,
            Game.game_date <= window_end,
            Game.game_status.in_(("scheduled", "in_progress")),
        )
        .all()
    )
    for game in stale_games:
        if game.espn_game_id and game.espn_game_id not in api_ids:
            game.game_status = "cancelled"
            cancelled_games += 1

    stale_schedules = (
        db.query(GameSchedule)
        .filter(
            GameSchedule.sport == "NBA",
            GameSchedule.game_date >= window_start,
            GameSchedule.game_date <= window_end,
            GameSchedule.status.in_(("scheduled", "in_progress")),
        )
        .all()
    )
    for sched in stale_schedules:
        ext = sched.external_game_id or sched.nba_game_id
        if ext and ext not in api_ids:
            sched.status = "cancelled"
            cancelled_schedules += 1

    return {"cancelled_games": cancelled_games, "cancelled_schedules": cancelled_schedules}


def resolve_nba_season_for_date(db: Session, game_date: date) -> Optional[Season]:
    season = (
        db.query(Season)
        .filter(
            Season.sport == "NBA",
            Season.start_date <= game_date,
            Season.end_date >= game_date,
        )
        .order_by(Season.is_current.desc())
        .first()
    )
    if season:
        return season
    return db.query(Season).filter(Season.sport == "NBA", Season.is_current.is_(True)).first()


def collect_schedule_range(
    db: Session, client, start: date, end: date, season: Optional[Season] = None
) -> Dict[str, int]:
    """Iterate day-by-day (ESPN scoreboard buckets by US date)."""
    totals = {
        "created_games": 0,
        "updated_games": 0,
        "created_schedules": 0,
        "updated_schedules": 0,
        "errors": 0,
    }
    all_api_games: List[Dict] = []
    current = start
    while current <= end:
        day_games = client.get_games_for_date(current)
        for g in day_games:
            g["game_date"] = current
        all_api_games.extend(day_games)
        day_season = season or resolve_nba_season_for_date(db, current)
        if day_season and day_games:
            result = persist_nba_schedule_games(db, day_games, day_season)
            for k in totals:
                totals[k] += result.get(k, 0)
        current += timedelta(days=1)

    rec = reconcile_nba_schedule_window(db, all_api_games, start, end)
    totals.update(rec)
    return totals
