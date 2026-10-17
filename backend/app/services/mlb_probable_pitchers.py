"""
Probable starting pitchers from the MLB Stats API schedule.

Pitcher props should only be generated for the listed probable starter per team.
"""
import re
import unicodedata
from datetime import date
from typing import Dict, List, Optional, TypedDict

from sqlalchemy.orm import Session

from app.models import Game, Player
from app.scrapers.mlb_api_client import MLBAPIClient, MLB_TEAM_ID_TO_ABBREV
from app.services.mlb_equivalent_props import MLB_PITCHER_PROP_STAT_TYPES


class ProbablePitcherInfo(TypedDict, total=False):
    id: Optional[int]
    name: Optional[str]


def normalize_mlb_person_name(name: str) -> str:
    if not name:
        return ''
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = text.replace('.', '').replace("'", '').replace('-', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text


def parse_box_score_style_name(name: str) -> Dict[str, str]:
    """
    Parse box-score style names: 'Martinez, N', 'Armstrong, S', or 'Jax'.
    """
    raw = (name or '').strip()
    if not raw:
        return {'last': '', 'first_initial': ''}
    if ',' in raw:
        last_part, first_part = raw.split(',', 1)
        last = normalize_mlb_person_name(last_part)
        first_tokens = normalize_mlb_person_name(first_part).split()
        fi = first_tokens[0][0] if first_tokens and first_tokens[0] else ''
        return {'last': last, 'first_initial': fi}
    return {'last': normalize_mlb_person_name(raw), 'first_initial': ''}


def parse_probable_pitcher_display_name(name: str) -> Dict[str, str]:
    """Parse schedule display names such as 'Nick Martinez' or 'Shawn Armstrong'."""
    tokens = normalize_mlb_person_name(name).split()
    if not tokens:
        return {'first': '', 'last': '', 'first_initial': ''}
    if len(tokens) == 1:
        return {'first': '', 'last': tokens[0], 'first_initial': ''}
    return {
        'first': tokens[0],
        'last': tokens[-1],
        'first_initial': tokens[0][0],
    }


def box_score_name_matches_probable(db_name: str, probable_name: str) -> bool:
    """Match 'Martinez, N' to API probable 'Nick Martinez'."""
    if normalize_mlb_person_name(db_name) == normalize_mlb_person_name(probable_name):
        return True
    box = parse_box_score_style_name(db_name)
    prob = parse_probable_pitcher_display_name(probable_name)
    if not box['last'] or not prob['last']:
        return False
    if box['last'] != prob['last']:
        return False
    if box['first_initial'] and prob['first_initial']:
        return box['first_initial'] == prob['first_initial']
    return True


def mlb_game_pk_from_game(game: Game) -> Optional[int]:
    box_id = game.espn_game_id or ''
    if box_id.startswith('MLB_'):
        try:
            return int(box_id[4:])
        except ValueError:
            return None
    return None


def _abbrev_for_mlb_team_id(mlb_team_id: int) -> Optional[str]:
    return MLB_TEAM_ID_TO_ABBREV.get(mlb_team_id)


def player_matches_probable(
    db: Session,
    player: Player,
    probable: ProbablePitcherInfo,
    team_id: int,
) -> bool:
    probable_id = probable.get('id')
    probable_name = probable.get('name')
    if not probable_name and not probable_id:
        return False

    if (
        probable_id is not None
        and player.mlb_person_id is not None
        and int(player.mlb_person_id) == int(probable_id)
    ):
        return True

    if probable_name and box_score_name_matches_probable(player.name, probable_name):
        return True

    if not probable_name:
        return False

    # Team-scoped fallback: unique roster match for this probable name / id
    roster = db.query(Player).filter(
        Player.sport == 'MLB',
        Player.current_team_id == team_id,
    ).all()
    matches: List[Player] = []
    for candidate in roster:
        if probable_id is not None and candidate.mlb_person_id is not None:
            if int(candidate.mlb_person_id) == int(probable_id):
                matches.append(candidate)
                continue
        if box_score_name_matches_probable(candidate.name, probable_name):
            matches.append(candidate)

    if len(matches) == 1 and matches[0].player_id == player.player_id:
        return True
    return False


class MlbProbablePitcherResolver:
    """Caches schedule lookups by game date and gamePk."""

    def __init__(self, client: Optional[MLBAPIClient] = None):
        self._client = client or MLBAPIClient(delay=0.0)
        self._by_pk: Dict[int, Dict] = {}
        self._dates_loaded: set = set()

    def _ensure_date_loaded(self, game_date: date) -> None:
        if game_date in self._dates_loaded:
            return
        games = self._client.get_schedule(game_date=game_date)
        for row in games or []:
            pk = row.get('game_id')
            if pk is None:
                continue
            home_id = row.get('home_id')
            away_id = row.get('away_id')
            home_name = (row.get('home_probable_pitcher') or '').strip() or None
            away_name = (row.get('away_probable_pitcher') or '').strip() or None
            home_pid = row.get('home_probable_pitcher_id')
            away_pid = row.get('away_probable_pitcher_id')
            self._by_pk[int(pk)] = {
                'home': _abbrev_for_mlb_team_id(home_id) if home_id else None,
                'away': _abbrev_for_mlb_team_id(away_id) if away_id else None,
                'home_probable': {'id': home_pid, 'name': home_name},
                'away_probable': {'id': away_pid, 'name': away_name},
            }
        self._dates_loaded.add(game_date)

    def probable_for_team(self, game: Game, team_id: int) -> Optional[ProbablePitcherInfo]:
        pk = mlb_game_pk_from_game(game)
        if pk is None:
            return None
        self._ensure_date_loaded(game.game_date)
        row = self._by_pk.get(pk)
        if not row:
            return None
        home = game.home_team
        away = game.away_team
        if not home or not away:
            return None
        if team_id == home.team_id:
            return row.get('home_probable')
        if team_id == away.team_id:
            return row.get('away_probable')
        return None

    def probable_name_for_team(self, game: Game, team_id: int) -> Optional[str]:
        info = self.probable_for_team(game, team_id)
        return info.get('name') if info else None

    def is_probable_pitcher(self, db: Session, game: Game, player: Player) -> bool:
        probable = self.probable_for_team(game, player.current_team_id)
        if not probable or not probable.get('name'):
            return False
        return player_matches_probable(
            db, player, probable, player.current_team_id
        )


def is_mlb_pitcher_prop_stat(stat_type: str) -> bool:
    return stat_type in MLB_PITCHER_PROP_STAT_TYPES


def should_skip_mlb_pitcher_prop(
    db: Session,
    game: Game,
    player: Player,
    stat_type: str,
    resolver: Optional[MlbProbablePitcherResolver] = None,
) -> bool:
    """
    Return True when a pitcher prop should NOT be generated.

    For scheduled/in-progress games, only the Stats API probable starter gets
    pitcher props. If no probable is listed for that team, skip all pitcher props.
    """
    if game.sport != 'MLB' or not is_mlb_pitcher_prop_stat(stat_type):
        return False
    if game.game_status not in ('scheduled', 'in_progress'):
        return False

    resolver = resolver or MlbProbablePitcherResolver()
    probable = resolver.probable_for_team(game, player.current_team_id)
    if not probable or not probable.get('name'):
        return True
    return not resolver.is_probable_pitcher(db, game, player)
