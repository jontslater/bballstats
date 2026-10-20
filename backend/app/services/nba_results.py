"""
Persist ESPN NBA finals into Game, PlayerGameStat, Lineup, and Injury rows.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Game, Injury, Lineup, Player, PlayerGameStat, Season, Team
from app.scrapers.espn_nba_client import ESPNNBAClient, normalize_nba_abbrev
from app.services.nba_schedule import find_nba_team, resolve_nba_season_for_date

NBA_RESULTS_LOOKBACK_DAYS = 7


def get_or_create_nba_player(
    db: Session,
    player_name: str,
    team: Team,
    espn_player_id: Optional[str] = None,
    position: Optional[str] = None,
) -> Player:
    player = None
    if espn_player_id:
        player = (
            db.query(Player)
            .filter(Player.sport == "NBA", Player.espn_player_id == str(espn_player_id))
            .first()
        )
    if not player:
        player = (
            db.query(Player)
            .filter(Player.sport == "NBA", Player.name == player_name, Player.current_team_id == team.team_id)
            .first()
        )
    if not player:
        player = db.query(Player).filter(Player.sport == "NBA", Player.name == player_name).first()

    if not player:
        max_id = db.query(func.max(Player.player_id)).filter(Player.sport == "NBA").scalar() or 0
        player = Player(
            player_id=max_id + 1,
            sport="NBA",
            name=player_name,
            position=position,
            current_team_id=team.team_id,
            espn_player_id=str(espn_player_id) if espn_player_id else None,
        )
        db.add(player)
        db.flush()
    else:
        if espn_player_id and not player.espn_player_id:
            player.espn_player_id = str(espn_player_id)
        if team and player.current_team_id != team.team_id:
            player.current_team_id = team.team_id
    return player


def _lookup_game(db: Session, espn_id: str, game_date: date, home_id: int, away_id: int) -> Optional[Game]:
    if espn_id:
        g = db.query(Game).filter(Game.sport == "NBA", Game.espn_game_id == espn_id).first()
        if g:
            return g
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


def _game_has_stats(db: Session, game_id: int) -> bool:
    return (
        db.query(PlayerGameStat.stat_id)
        .filter(PlayerGameStat.sport == "NBA", PlayerGameStat.game_id == game_id)
        .first()
        is not None
    )


def upsert_injuries_for_game(db: Session, game_date: date, injuries: List[Dict]) -> int:
    written = 0
    for inj in injuries:
        team = find_nba_team(db, inj.get("team_abbreviation"))
        if not team or not inj.get("player_name"):
            continue
        player = get_or_create_nba_player(
            db,
            inj["player_name"],
            team,
            espn_player_id=inj.get("espn_player_id"),
        )
        status = inj.get("status") or "Unknown"
        existing = (
            db.query(Injury)
            .filter(Injury.player_id == player.player_id, Injury.injury_date == game_date)
            .first()
        )
        if existing:
            existing.status = status
            existing.injury_type = inj.get("injury_type") or existing.injury_type
            existing.description = inj.get("description") or existing.description
            existing.source = "ESPN"
        else:
            db.add(
                Injury(
                    player_id=player.player_id,
                    injury_date=game_date,
                    injury_type=inj.get("injury_type"),
                    status=status,
                    description=inj.get("description"),
                    source="ESPN",
                )
            )
        written += 1
    return written


def upsert_lineup_starters(db: Session, game: Game, player_stats: List[Dict]) -> int:
    count = 0
    for ps in player_stats:
        if not ps.get("is_starter"):
            continue
        team = find_nba_team(db, ps.get("team_abbreviation"))
        if not team:
            continue
        player = get_or_create_nba_player(
            db,
            ps["player_name"],
            team,
            espn_player_id=ps.get("espn_player_id"),
        )
        existing = (
            db.query(Lineup)
            .filter(Lineup.game_id == game.game_id, Lineup.player_id == player.player_id)
            .first()
        )
        if existing:
            existing.is_starter = True
            existing.team_id = team.team_id
        else:
            db.add(
                Lineup(
                    game_id=game.game_id,
                    team_id=team.team_id,
                    player_id=player.player_id,
                    is_starter=True,
                )
            )
        count += 1
    return count


def upsert_final_from_espn(
    db: Session,
    client: ESPNNBAClient,
    api_game: Dict,
    season: Season,
    skip_if_complete: bool = True,
) -> Tuple[Optional[Game], bool, int]:
    """
    Fetch summary/box score and persist. Returns (game, created, stats_written).
    """
    if api_game.get("status") != "finished":
        return None, False, 0

    home = find_nba_team(db, api_game.get("home_team"))
    away = find_nba_team(db, api_game.get("away_team"))
    if not home or not away:
        return None, False, 0

    espn_id = str(api_game["espn_game_id"])
    game_date = api_game["game_date"]

    existing = _lookup_game(db, espn_id, game_date, home.team_id, away.team_id)
    if existing and skip_if_complete and existing.game_status == "finished" and _game_has_stats(db, existing.game_id):
        return existing, False, 0

    box = client.get_box_score_for_game(espn_id, game_meta=api_game)
    if not box or not box.get("player_stats"):
        return None, False, 0

    home_score = box.get("home_score") if box.get("home_score") is not None else api_game.get("home_score")
    away_score = box.get("away_score") if box.get("away_score") is not None else api_game.get("away_score")

    created = False
    if existing:
        game = existing
    else:
        game = Game(
            sport="NBA",
            game_date=game_date,
            season_id=season.season_id,
            home_team_id=home.team_id,
            away_team_id=away.team_id,
            espn_game_id=espn_id,
        )
        db.add(game)
        db.flush()
        created = True

    game.home_score = home_score
    game.away_score = away_score
    game.game_status = "finished"
    game.espn_game_id = espn_id

    stats_written = 0
    for ps in box["player_stats"]:
        team_abbrev = normalize_nba_abbrev(ps.get("team_abbreviation"))
        team = find_nba_team(db, team_abbrev)
        if not team:
            continue
        opponent = away if team.team_id == home.team_id else home
        player = get_or_create_nba_player(
            db,
            ps["player_name"],
            team,
            espn_player_id=ps.get("espn_player_id"),
        )
        dup = (
            db.query(PlayerGameStat)
            .filter(PlayerGameStat.player_id == player.player_id, PlayerGameStat.game_id == game.game_id)
            .first()
        )
        if dup:
            continue
        db.add(
            PlayerGameStat(
                sport="NBA",
                player_id=player.player_id,
                game_id=game.game_id,
                team_id=team.team_id,
                opponent_team_id=opponent.team_id,
                minutes_played=ps.get("minutes_played"),
                points=ps.get("points"),
                rebounds=ps.get("rebounds"),
                offensive_rebounds=ps.get("offensive_rebounds"),
                defensive_rebounds=ps.get("defensive_rebounds"),
                assists=ps.get("assists"),
                steals=ps.get("steals"),
                blocks=ps.get("blocks"),
                turnovers=ps.get("turnovers"),
                personal_fouls=ps.get("personal_fouls"),
                field_goals_made=ps.get("field_goals_made"),
                field_goals_attempted=ps.get("field_goals_attempted"),
                three_pointers_made=ps.get("three_pointers_made"),
                three_pointers_attempted=ps.get("three_pointers_attempted"),
                free_throws_made=ps.get("free_throws_made"),
                free_throws_attempted=ps.get("free_throws_attempted"),
                plus_minus=ps.get("plus_minus"),
                is_home=team.team_id == home.team_id,
            )
        )
        stats_written += 1

    upsert_lineup_starters(db, game, box["player_stats"])
    upsert_injuries_for_game(db, game_date, box.get("injuries") or [])

    return game, created, stats_written


def collect_games_for_date(
    db: Session,
    client: ESPNNBAClient,
    game_date: date,
    skip_if_has_stats: bool = False,
) -> Tuple[int, int]:
    """Returns (games_created, games_processed)."""
    season = resolve_nba_season_for_date(db, game_date)
    if not season:
        return 0, 0

    api_games = client.get_games_for_date(game_date)
    for g in api_games:
        g["game_date"] = game_date

    created = processed = 0
    for api_game in api_games:
        if api_game.get("status") != "finished":
            continue
        if skip_if_has_stats and api_game.get("espn_game_id"):
            existing = db.query(Game).filter(
                Game.sport == "NBA", Game.espn_game_id == str(api_game["espn_game_id"])
            ).first()
            if existing and _game_has_stats(db, existing.game_id):
                continue
        _, was_created, n_stats = upsert_final_from_espn(db, client, api_game, season)
        if n_stats > 0 or was_created:
            processed += 1
            if was_created:
                created += 1
    return created, processed
