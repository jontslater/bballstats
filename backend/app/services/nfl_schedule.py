"""
Persist NFL schedules from ESPN (and link Game rows for predictions).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Game, GameSchedule, Season, Team
from app.services.nfl_data import parse_espn_status


def find_nfl_team(db: Session, abbrev: str) -> Optional[Team]:
    if not abbrev:
        return None
    return db.query(Team).filter(
        Team.sport == "NFL",
        Team.abbreviation == abbrev.upper(),
    ).first()


def persist_espn_games(db: Session, games: List[Dict], season: Season) -> Dict[str, int]:
    """Upsert GameSchedule + Game rows from ESPN game dicts."""
    created = updated = errors = 0

    for game_data in games:
        try:
            home_abbrev = game_data.get("home_team")
            away_abbrev = game_data.get("away_team")
            home_team = find_nfl_team(db, home_abbrev)
            away_team = find_nfl_team(db, away_abbrev)
            if not home_team or not away_team:
                errors += 1
                continue

            game_date = game_data.get("game_date")
            external_id = game_data.get("espn_game_id")
            status = parse_espn_status(game_data.get("status", "scheduled"))
            home_score = game_data.get("home_score")
            away_score = game_data.get("away_score")

            existing_schedule = None
            if external_id:
                existing_schedule = db.query(GameSchedule).filter(
                    GameSchedule.sport == "NFL",
                    GameSchedule.external_game_id == str(external_id),
                ).first()
            if not existing_schedule:
                existing_schedule = db.query(GameSchedule).filter(
                    GameSchedule.sport == "NFL",
                    GameSchedule.game_date == game_date,
                    GameSchedule.home_team_id == home_team.team_id,
                    GameSchedule.away_team_id == away_team.team_id,
                ).first()

            if existing_schedule:
                existing_schedule.external_game_id = external_id or existing_schedule.external_game_id
                existing_schedule.status = status
                updated += 1
                schedule = existing_schedule
            else:
                schedule = GameSchedule(
                    sport="NFL",
                    game_date=game_date,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    season_id=season.season_id,
                    external_game_id=str(external_id) if external_id else None,
                    status=status,
                )
                db.add(schedule)
                created += 1

            # Finished games → Game row with scores
            if status == "finished" and home_score is not None and away_score is not None:
                game = None
                if external_id:
                    game = db.query(Game).filter(
                        Game.sport == "NFL",
                        Game.espn_game_id == str(external_id),
                    ).first()
                if not game:
                    game = db.query(Game).filter(
                        Game.sport == "NFL",
                        Game.game_date == game_date,
                        Game.home_team_id == home_team.team_id,
                        Game.away_team_id == away_team.team_id,
                    ).first()
                if game:
                    game.home_score = home_score
                    game.away_score = away_score
                    game.game_status = "finished"
                    if external_id and not game.espn_game_id:
                        game.espn_game_id = str(external_id)
                    schedule.game_id = game.game_id
                else:
                    game = Game(
                        sport="NFL",
                        game_date=game_date,
                        season_id=season.season_id,
                        home_team_id=home_team.team_id,
                        away_team_id=away_team.team_id,
                        home_score=home_score,
                        away_score=away_score,
                        game_status="finished",
                        espn_game_id=str(external_id) if external_id else None,
                    )
                    db.add(game)
                    db.flush()
                    schedule.game_id = game.game_id
            elif status in ("scheduled", "in_progress"):
                game = None
                if external_id:
                    game = db.query(Game).filter(
                        Game.sport == "NFL",
                        Game.espn_game_id == str(external_id),
                    ).first()
                if not game:
                    game = db.query(Game).filter(
                        Game.sport == "NFL",
                        Game.game_date == game_date,
                        Game.home_team_id == home_team.team_id,
                        Game.away_team_id == away_team.team_id,
                    ).first()
                if not game:
                    game = Game(
                        sport="NFL",
                        game_date=game_date,
                        season_id=season.season_id,
                        home_team_id=home_team.team_id,
                        away_team_id=away_team.team_id,
                        game_status=status,
                        espn_game_id=str(external_id) if external_id else None,
                    )
                    db.add(game)
                    db.flush()
                else:
                    game.game_status = status
                    if external_id and not game.espn_game_id:
                        game.espn_game_id = str(external_id)
                schedule.game_id = game.game_id

        except Exception:
            errors += 1
            continue

    db.commit()
    return {"created": created, "updated": updated, "errors": errors}


def sync_upcoming_schedule_window(
    db: Session,
    espn_client,
    season: Season,
    lookback_days: int = 7,
    days_ahead: int = 14,
) -> Dict[str, int]:
    """
    Pull ESPN scoreboard day-by-day for a rolling window (handles bye weeks cleanly).
    """
    today = date.today()
    start = today - timedelta(days=lookback_days)
    end = today + timedelta(days=days_ahead)

    all_games: List[Dict] = []
    cursor = start
    while cursor <= end:
        all_games.extend(espn_client.get_games_for_date(cursor))
        cursor += timedelta(days=1)

    return persist_espn_games(db, all_games, season)
