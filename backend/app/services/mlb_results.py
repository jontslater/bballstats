"""
Persist MLB Stats API finals into Game + PlayerGameStat.

Daily results collection used to only process --previous-day, so a missed
morning run left finished games stuck as scheduled with no scores. Matching
is by espn_game_id = MLB_<gamePk> first (the schedule persist key).
"""
from datetime import date, datetime
from typing import Dict, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Game, Player, PlayerGameStat, Season, Team
from app.scrapers.mlb_api_client import MLBAPIClient
from app.services.mlb_schedule import find_mlb_team, mlb_external_game_id, _lookup_existing_game

MLB_RESULTS_LOOKBACK_DAYS = 7
MLB_FINAL_API_STATUSES = ('Final', 'Game Over', 'Completed Early')


def get_or_create_mlb_player(
    db: Session,
    player_name: str,
    team: Team,
    position: str = None,
    is_batter: bool = False,
    is_pitcher: bool = False,
):
    """Get or create MLB player by name and team."""
    player = db.query(Player).filter(
        Player.sport == 'MLB',
        Player.name == player_name
    ).first()

    if not player:
        if not position:
            if is_pitcher:
                position = 'P'
            elif is_batter:
                position = 'DH'
            else:
                position = 'P'

        player = Player(
            sport='MLB',
            name=player_name,
            position=position,
            current_team_id=team.team_id
        )
        db.add(player)
        db.flush()
    else:
        if player.current_team_id != team.team_id:
            player.current_team_id = team.team_id

        if position and player.position == 'P' and is_batter and not is_pitcher:
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


def _game_already_complete(db: Session, game: Game) -> bool:
    if game.game_status != 'finished':
        return False
    if game.home_score is None or game.away_score is None:
        return False
    has_stats = db.query(PlayerGameStat.stat_id).filter(
        PlayerGameStat.sport == 'MLB',
        PlayerGameStat.game_id == game.game_id,
    ).first()
    return has_stats is not None


def _coerce_score(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def upsert_mlb_final_game(
    db: Session,
    client: MLBAPIClient,
    api_game: Dict,
    season: Season,
) -> Tuple[Optional[Game], bool]:
    """
    Match by espn_game_id MLB_<gamePk> first, then date+teams.
    Updates the existing Game in place (no duplicates). Returns (game, created).
    """
    home_id = api_game.get('home_id')
    away_id = api_game.get('away_id')
    home_abbrev = client.get_team_abbrev(home_id) if home_id else None
    away_abbrev = client.get_team_abbrev(away_id) if away_id else None
    if not home_abbrev or not away_abbrev:
        return None, False

    home_team = find_mlb_team(db, home_abbrev)
    away_team = find_mlb_team(db, away_abbrev)
    if not home_team or not away_team or home_team.team_id == away_team.team_id:
        return None, False

    game_pk = api_game.get('game_id')
    box_id = mlb_external_game_id(game_pk)
    raw_date = api_game.get('game_date')
    if isinstance(raw_date, date) and not isinstance(raw_date, datetime):
        game_date_obj = raw_date
    else:
        game_date_obj = datetime.strptime(str(raw_date)[:10], '%Y-%m-%d').date()

    existing = _lookup_existing_game(
        db, box_id, game_date_obj, home_team.team_id, away_team.team_id
    )
    created = False
    if existing and _game_already_complete(db, existing):
        return existing, False

    box_data = client.get_box_score_data(game_pk)
    if not box_data:
        return None, False

    parsed = client.parse_box_score_for_db(box_data, home_abbrev, away_abbrev)
    away_score = _coerce_score(parsed.get('away_score') if parsed else None)
    if away_score is None:
        away_score = _coerce_score(api_game.get('away_score'))
    home_score = _coerce_score(parsed.get('home_score') if parsed else None)
    if home_score is None:
        home_score = _coerce_score(api_game.get('home_score'))

    if existing:
        game = existing
        if away_score is not None:
            game.away_score = away_score
        if home_score is not None:
            game.home_score = home_score
        game.game_status = 'finished'
        if box_id and game.espn_game_id != box_id:
            game.espn_game_id = box_id
    else:
        game = Game(
            sport='MLB',
            game_date=game_date_obj,
            season_id=season.season_id,
            home_team_id=home_team.team_id,
            away_team_id=away_team.team_id,
            home_score=home_score,
            away_score=away_score,
            game_status='finished',
            espn_game_id=box_id,
        )
        db.add(game)
        db.flush()
        created = True

    for ps in (parsed or {}).get('player_stats', []):
        try:
            with db.begin_nested():
                team_abbr = ps.get('team_abbreviation')
                team = find_mlb_team(db, team_abbr) if team_abbr else None
                if not team:
                    continue
                opponent = away_team if team.team_id == home_team.team_id else home_team

                is_batter = ps.get('is_batter', False)
                is_pitcher = ps.get('is_pitcher', False)
                position = ps.get('position')
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
        except Exception:
            continue

    return game, created


def collect_games_for_date(
    db: Session,
    client: MLBAPIClient,
    game_date: date,
    skip_if_has_stats: bool = False
) -> Tuple[int, int]:
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

    try:
        games = client.get_schedule(game_date=game_date)
    except Exception as e:
        print(f"  MLB API schedule error for {game_date}: {e}")
        return 0, 0

    games = [g for g in (games or []) if g.get('status') in MLB_FINAL_API_STATUSES]
    if not games:
        return 0, 0

    games_created = games_processed = 0
    for g in games:
        try:
            game, created = upsert_mlb_final_game(db, client, g, season)
            if not game:
                continue
            db.commit()
            if created:
                games_created += 1
            games_processed += 1
        except Exception as e:
            db.rollback()
            print(f"Error: {e}")
            continue

    return games_created, games_processed
