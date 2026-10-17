"""
Probable starting pitchers from the MLB Stats API schedule.

Pitcher props should only be generated for the listed probable starter per team.
"""
import re
import unicodedata
from datetime import date
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Game, Player
from app.scrapers.mlb_api_client import MLBAPIClient, MLB_TEAM_ID_TO_ABBREV
from app.services.mlb_equivalent_props import MLB_PITCHER_PROP_STAT_TYPES


def normalize_mlb_person_name(name: str) -> str:
    if not name:
        return ''
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = text.replace('.', '').replace("'", '').replace('-', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text


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


class MlbProbablePitcherResolver:
    """Caches schedule lookups by game date and gamePk."""

    def __init__(self, client: Optional[MLBAPIClient] = None):
        self._client = client or MLBAPIClient(delay=0.0)
        self._by_pk: Dict[int, Dict[str, Optional[str]]] = {}
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
            self._by_pk[int(pk)] = {
                'home': _abbrev_for_mlb_team_id(home_id) if home_id else None,
                'away': _abbrev_for_mlb_team_id(away_id) if away_id else None,
                'home_probable': (row.get('home_probable_pitcher') or '').strip() or None,
                'away_probable': (row.get('away_probable_pitcher') or '').strip() or None,
            }
        self._dates_loaded.add(game_date)

    def probable_name_for_team(self, game: Game, team_id: int) -> Optional[str]:
        """Probable starter name for team_id, or None if not listed."""
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
            expected_abbrev = row.get('home')
            probable = row.get('home_probable')
        elif team_id == away.team_id:
            expected_abbrev = row.get('away')
            probable = row.get('away_probable')
        else:
            return None
        if expected_abbrev and home.abbreviation == expected_abbrev:
            pass
        elif expected_abbrev and away.abbreviation == expected_abbrev:
            pass
        return probable

    def is_probable_pitcher(self, game: Game, player: Player) -> bool:
        probable = self.probable_name_for_team(game, player.current_team_id)
        if not probable:
            return False
        return normalize_mlb_person_name(player.name) == normalize_mlb_person_name(probable)


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

    pos = (player.position or '').upper()
    if pos not in ('P', 'SP', 'RP') and stat_type == 'strikeouts':
        # Two-way / mis-tagged positions: still treat as pitcher only when SO prop
        pass

    resolver = resolver or MlbProbablePitcherResolver()
    probable = resolver.probable_name_for_team(game, player.current_team_id)
    if not probable:
        return True
    return not resolver.is_probable_pitcher(game, player)
