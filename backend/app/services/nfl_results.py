"""
NFL game results + player box scores (ESPN summary + nflverse backfill).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Game, Player, PlayerGameStat, Season, Team
from app.scrapers.espn_nfl_client import ESPNNFLClient
from app.services.nfl_data import (
    game_lookup_key,
    load_nflverse_games,
    load_nflverse_player_stats,
    normalize_team_abbrev,
)
from app.services.nfl_schedule import find_nfl_team


NFL_RESULTS_LOOKBACK_DAYS = 7


def get_or_create_nfl_player(
    db: Session,
    player_name: str,
    team: Team,
    position: Optional[str] = None,
) -> Player:
    player = db.query(Player).filter(
        Player.sport == "NFL",
        Player.name == player_name,
    ).first()
    if not player:
        player = Player(
            sport="NFL",
            name=player_name,
            position=position,
            current_team_id=team.team_id,
        )
        db.add(player)
        db.flush()
    else:
        if position and not player.position:
            player.position = position
        if team and player.current_team_id != team.team_id:
            player.current_team_id = team.team_id
    return player


def _merge_stat_row(existing: PlayerGameStat, values: Dict) -> None:
    for field, val in values.items():
        if val is not None:
            setattr(existing, field, val)


def collect_game_from_espn_summary(
    db: Session,
    game: Game,
    client: Optional[ESPNNFLClient] = None,
) -> int:
    """Pull box score for one finished/scheduled game with espn_game_id."""
    if not game.espn_game_id:
        return 0
    client = client or ESPNNFLClient()
    summary = client.get_game_summary(game.espn_game_id)
    if not summary:
        return 0

    rows = client.parse_box_score_players(summary)
    saved = 0
    home = game.home_team
    away = game.away_team

    for row in rows:
        team_abbrev = normalize_team_abbrev(row.get("team_abbrev"))
        if team_abbrev == home.abbreviation:
            team = home
            opponent = away
        elif team_abbrev == away.abbreviation:
            team = away
            opponent = home
        else:
            continue

        player = get_or_create_nfl_player(
            db,
            row["player_name"],
            team,
            row.get("position"),
        )

        stat_values = {
            "passing_yards": row.get("passing_yards"),
            "passing_tds": row.get("passing_tds"),
            "interceptions": row.get("interceptions"),
            "completions": row.get("completions"),
            "pass_attempts": row.get("pass_attempts"),
            "rushing_yards": row.get("rushing_yards"),
            "rushing_tds": row.get("rushing_tds"),
            "rushing_attempts": row.get("rushing_attempts"),
            "receptions": row.get("receptions"),
            "receiving_yards": row.get("receiving_yards"),
            "receiving_tds": row.get("receiving_tds"),
            "targets": row.get("targets"),
        }

        if not any(v is not None and v != 0 for v in stat_values.values()):
            continue

        existing = db.query(PlayerGameStat).filter(
            PlayerGameStat.sport == "NFL",
            PlayerGameStat.player_id == player.player_id,
            PlayerGameStat.game_id == game.game_id,
        ).first()

        if existing:
            _merge_stat_row(existing, stat_values)
        else:
            pgs = PlayerGameStat(
                sport="NFL",
                player_id=player.player_id,
                game_id=game.game_id,
                team_id=team.team_id,
                opponent_team_id=opponent.team_id,
                **stat_values,
            )
            db.add(pgs)
        saved += 1

    # Mark final from header if present
    header = summary.get("header") or {}
    comp = (header.get("competitions") or [{}])[0]
    status_type = (comp.get("status") or {}).get("type", {}).get("name", "")
    if "FINAL" in (status_type or "").upper():
        game.game_status = "finished"
        for comp_team in comp.get("competitors") or []:
            score = comp_team.get("score")
            if comp_team.get("homeAway") == "home" and score is not None:
                game.home_score = int(score)
            if comp_team.get("homeAway") == "away" and score is not None:
                game.away_score = int(score)

    db.commit()
    return saved


def collect_results_lookback(
    db: Session,
    lookback_days: int = NFL_RESULTS_LOOKBACK_DAYS,
) -> Dict[str, int]:
    """Collect ESPN box scores for recent NFL games."""
    client = ESPNNFLClient()
    cutoff = date.today() - timedelta(days=lookback_days)
    games = db.query(Game).filter(
        Game.sport == "NFL",
        Game.game_date >= cutoff,
        Game.game_date <= date.today(),
        Game.espn_game_id.isnot(None),
    ).all()

    stats_saved = 0
    games_processed = 0
    for game in games:
        try:
            stats_saved += collect_game_from_espn_summary(db, game, client)
            games_processed += 1
        except Exception:
            db.rollback()
            continue

    return {"games_processed": games_processed, "player_rows": stats_saved}


def backfill_from_nflverse(
    db: Session,
    seasons: List[int],
    skip_existing: bool = True,
) -> Dict[str, int]:
    """
    Bulk import schedules + weekly player stats from nflverse CSVs.
    """
    games_df = load_nflverse_games(seasons)
    stats_df = load_nflverse_player_stats(seasons)

    season_by_year: Dict[int, Season] = {}
    for year in seasons:
        season = db.query(Season).filter(
            Season.sport == "NFL",
            Season.season_year == str(year),
        ).first()
        if season:
            season_by_year[year] = season

    game_id_by_key: Dict[Tuple[str, str, date], int] = {}
    games_created = 0
    stats_created = 0
    stats_updated = 0

    for _, row in games_df.iterrows():
        year = int(row["season"])
        season = season_by_year.get(year)
        if not season:
            continue
        if row.get("game_type") != "REG":
            continue

        home = find_nfl_team(db, row["home_team"])
        away = find_nfl_team(db, row["away_team"])
        if not home or not away:
            continue

        gday = row["gameday"]
        key = game_lookup_key(home.abbreviation, away.abbreviation, gday)

        espn_id = None
        if pd_notna(row.get("espn")):
            espn_id = str(int(row["espn"])) if float(row["espn"]).is_integer() else str(row["espn"])

        game = db.query(Game).filter(
            Game.sport == "NFL",
            Game.game_date == gday,
            Game.home_team_id == home.team_id,
            Game.away_team_id == away.team_id,
        ).first()
        if not game:
            status = "finished" if pd_notna(row.get("home_score")) else "scheduled"
            game = Game(
                sport="NFL",
                game_date=gday,
                season_id=season.season_id,
                home_team_id=home.team_id,
                away_team_id=away.team_id,
                home_score=int(row["home_score"]) if pd_notna(row.get("home_score")) else None,
                away_score=int(row["away_score"]) if pd_notna(row.get("away_score")) else None,
                game_status=status,
                espn_game_id=espn_id,
            )
            db.add(game)
            db.flush()
            games_created += 1
        else:
            if espn_id and not game.espn_game_id:
                game.espn_game_id = espn_id
            if pd_notna(row.get("home_score")):
                game.home_score = int(row["home_score"])
                game.away_score = int(row["away_score"])
                game.game_status = "finished"

        game_id_by_key[key] = game.game_id

    db.commit()

    for _, row in stats_df.iterrows():
        year = int(row["season"])
        if year not in season_by_year:
            continue
        if row.get("season_type") != "REG":
            continue

        team = find_nfl_team(db, row["recent_team"])
        opp = find_nfl_team(db, row["opponent_team"])
        if not team or not opp:
            continue

        week = int(row["week"])
        opp_abbrev = normalize_team_abbrev(row.get("opponent_team"))
        week_games = games_df[
            (games_df["season"] == year)
            & (games_df["week"] == week)
            & (
                (
                    (games_df["home_team"] == team.abbreviation)
                    & (games_df["away_team"] == opp_abbrev)
                )
                | (
                    (games_df["home_team"] == opp_abbrev)
                    & (games_df["away_team"] == team.abbreviation)
                )
            )
        ]
        if week_games.empty:
            continue
        match = week_games.iloc[0]
        gday = match["gameday"]
        home = find_nfl_team(db, match["home_team"])
        away = find_nfl_team(db, match["away_team"])
        if not home or not away:
            continue
        key = game_lookup_key(home.abbreviation, away.abbreviation, gday)
        game_id = game_id_by_key.get(key)
        if not game_id:
            continue

        name = row.get("player_display_name") or row.get("player_name")
        if not name or (isinstance(name, float) and str(name) == "nan"):
            continue

        player = get_or_create_nfl_player(db, str(name), team, row.get("position"))

        if skip_existing:
            exists = db.query(PlayerGameStat.stat_id).filter(
                PlayerGameStat.sport == "NFL",
                PlayerGameStat.player_id == player.player_id,
                PlayerGameStat.game_id == game_id,
            ).first()
            if exists:
                continue

        values = {
            "passing_yards": _int_or_none(row.get("passing_yards")),
            "passing_tds": _int_or_none(row.get("passing_tds")),
            "interceptions": _int_or_none(row.get("interceptions")),
            "completions": _int_or_none(row.get("completions")),
            "pass_attempts": _int_or_none(row.get("attempts")),
            "rushing_yards": _int_or_none(row.get("rushing_yards")),
            "rushing_tds": _int_or_none(row.get("rushing_tds")),
            "rushing_attempts": _int_or_none(row.get("carries")),
            "receptions": _int_or_none(row.get("receptions")),
            "receiving_yards": _int_or_none(row.get("receiving_yards")),
            "receiving_tds": _int_or_none(row.get("receiving_tds")),
            "targets": _int_or_none(row.get("targets")),
        }
        if not any(v is not None and v != 0 for v in values.values()):
            continue

        opp_team = find_nfl_team(db, opp_abbrev)
        opponent_id = opp_team.team_id if opp_team else (
            away.team_id if team.team_id == home.team_id else home.team_id
        )
        pgs = PlayerGameStat(
            sport="NFL",
            player_id=player.player_id,
            game_id=game_id,
            team_id=team.team_id,
            opponent_team_id=opponent_id,
            **values,
        )
        db.add(pgs)
        stats_created += 1

        if stats_created % 500 == 0:
            db.commit()

    db.commit()
    return {
        "games_created": games_created,
        "stats_created": stats_created,
        "stats_updated": stats_updated,
    }


def pd_notna(val) -> bool:
    try:
        import pandas as pd

        return pd.notna(val)
    except Exception:
        return val is not None


def _int_or_none(val) -> Optional[int]:
    if val is None:
        return None
    try:
        import pandas as pd

        if pd.isna(val):
            return None
    except Exception:
        pass
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def date_has_nfl_stats(db: Session, game_date: date) -> bool:
    count = db.query(func.count(PlayerGameStat.stat_id)).join(
        Game, PlayerGameStat.game_id == Game.game_id
    ).filter(
        PlayerGameStat.sport == "NFL",
        Game.game_date == game_date,
    ).scalar()
    return (count or 0) > 0
