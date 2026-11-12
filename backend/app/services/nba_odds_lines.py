"""
Ingest NBA player prop lines from The Odds API into BettingLine rows.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Game, Player, Prediction, Team
from app.scrapers.odds_api_client import OddsApiClient, NBA_SPORT_KEY
from app.services.betting_line_service import BettingLineService

logger = logging.getLogger(__name__)

CENTRAL = ZoneInfo("America/Chicago")

DEFAULT_MARKETS = (
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_points_rebounds_assists",
)

MARKET_TO_STAT_TYPE = {
    "player_points": "points",
    "player_rebounds": "rebounds",
    "player_assists": "assists",
    "player_points_rebounds_assists": "pts+ast+reb",
}

DEFAULT_BOOKMAKER_PRIORITY = ("fanduel", "draftkings")

BOOKMAKER_DISPLAY = {
    "fanduel": "FanDuel",
    "draftkings": "DraftKings",
}

NBA_TEAM_NAME_ALIASES = {
    "los angeles clippers": "la clippers",
    "la clippers": "la clippers",
    "los angeles lakers": "los angeles lakers",
    "golden state warriors": "golden state warriors",
    "new york knicks": "new york knicks",
    "brooklyn nets": "brooklyn nets",
    "san antonio spurs": "san antonio spurs",
    "oklahoma city thunder": "oklahoma city thunder",
    "new orleans pelicans": "new orleans pelicans",
}


@dataclass
class IngestSummary:
    events_considered: int = 0
    events_fetched: int = 0
    lines_upserted: int = 0
    lines_dry_run: int = 0
    unmatched_players: Set[str] = field(default_factory=set)
    unmatched_games: List[str] = field(default_factory=list)
    skipped_no_game: int = 0
    skipped_predictions_filter: int = 0


def normalize_team_name(name: str) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return NBA_TEAM_NAME_ALIASES.get(text, text)


_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b", re.IGNORECASE)


def normalize_player_name(name: str) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = text.replace(".", "").replace("'", "").replace("-", " ")
    text = _SUFFIX_RE.sub("", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def american_odds_str(price: Any) -> str:
    if price is None:
        return ""
    if isinstance(price, str):
        s = price.strip()
        if s.startswith("+") or s.startswith("-"):
            return s
        try:
            price = int(float(s))
        except (TypeError, ValueError):
            return s
    try:
        n = int(price)
    except (TypeError, ValueError):
        return str(price)
    if n > 0:
        return f"+{n}"
    return str(n)


def event_commence_central_date(event: Dict[str, Any]) -> Optional[date]:
    raw = event.get("commence_time")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.astimezone(CENTRAL).date()
    except (ValueError, TypeError):
        return None


def _build_team_lookup(db: Session) -> Dict[str, Team]:
    lookup: Dict[str, Team] = {}
    for team in db.query(Team).filter(Team.sport == "NBA").all():
        lookup[normalize_team_name(team.name)] = team
    return lookup


def find_game_for_event(
    db: Session,
    event: Dict[str, Any],
    target_date: date,
    team_lookup: Dict[str, Team],
) -> Optional[Game]:
    home = team_lookup.get(normalize_team_name(event.get("home_team", "")))
    away = team_lookup.get(normalize_team_name(event.get("away_team", "")))
    if not home or not away:
        label = f"{event.get('away_team')} @ {event.get('home_team')} ({target_date})"
        logger.warning("Unmatched teams for odds event: %s", label)
        return None
    game = (
        db.query(Game)
        .filter(
            Game.sport == "NBA",
            Game.game_date == target_date,
            Game.home_team_id == home.team_id,
            Game.away_team_id == away.team_id,
        )
        .first()
    )
    if not game:
        label = f"{away.abbreviation} @ {home.abbreviation} on {target_date}"
        logger.warning("No DB game for odds event: %s (event id %s)", label, event.get("id"))
    return game


def _players_for_game_teams(db: Session, home_team_id: int, away_team_id: int) -> List[Player]:
    return (
        db.query(Player)
        .filter(
            Player.sport == "NBA",
            Player.current_team_id.in_((home_team_id, away_team_id)),
        )
        .all()
    )


def match_player_id(
    player_name: str,
    roster: Sequence[Player],
) -> Optional[int]:
    target = normalize_player_name(player_name)
    if not target:
        return None
    exact = [p for p in roster if normalize_player_name(p.name) == target]
    if len(exact) == 1:
        return exact[0].player_id
    if len(exact) > 1:
        return None
    parts = target.split()
    if len(parts) >= 2:
        last = parts[-1]
        first = parts[0]
        candidates = [
            p
            for p in roster
            if normalize_player_name(p.name).split()[-1:] == [last]
            and normalize_player_name(p.name).split()[0:1] == [first]
        ]
        if len(candidates) == 1:
            return candidates[0].player_id
    return None


def _game_ids_with_predictions(db: Session, target_date: date) -> Set[int]:
    rows = (
        db.query(Prediction.game_id)
        .join(Game, Game.game_id == Prediction.game_id)
        .filter(
            Game.sport == "NBA",
            Game.game_date == target_date,
            Prediction.sport == "NBA",
            Prediction.bet_type != "pass",
        )
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def _pick_market_outcomes(
    odds_payload: Dict[str, Any],
    market_keys: Sequence[str],
    bookmaker_priority: Sequence[str],
) -> Dict[str, Tuple[str, List[Dict[str, Any]]]]:
    """
    Per-market bookmaker selection (FanDuel first, DraftKings fallback per market).
    Returns market_key -> (bookmaker_key, outcomes).
    """
    bookmakers = {b.get("key"): b for b in odds_payload.get("bookmakers") or [] if b.get("key")}
    selected: Dict[str, Tuple[str, List[Dict[str, Any]]]] = {}
    for mkey in market_keys:
        for book_key in bookmaker_priority:
            book = bookmakers.get(book_key)
            if not book:
                continue
            for market in book.get("markets") or []:
                if market.get("key") == mkey and market.get("outcomes"):
                    selected[mkey] = (book_key, market.get("outcomes") or [])
                    break
            if mkey in selected:
                break
    return selected


def _pick_bookmaker_markets(
    odds_payload: Dict[str, Any],
    market_keys: Sequence[str],
    bookmaker_priority: Sequence[str],
) -> Tuple[Optional[str], Dict[str, List[Dict[str, Any]]]]:
    """Legacy helper: returns primary book + outcomes (prefer FanDuel if any market hit)."""
    per_market = _pick_market_outcomes(odds_payload, market_keys, bookmaker_priority)
    if not per_market:
        return None, {}
    primary = bookmaker_priority[0] if bookmaker_priority else next(iter(per_market.values()))[0]
    return primary, {k: v[1] for k, v in per_market.items()}


def _parse_prop_outcomes(
    outcomes: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Map normalized player name -> {line, over_price, under_price}."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for outcome in outcomes:
        side = (outcome.get("name") or "").strip().lower()
        player_raw = outcome.get("description") or outcome.get("name") or ""
        if side not in ("over", "under"):
            continue
        norm = normalize_player_name(player_raw)
        if not norm:
            continue
        bucket = grouped.setdefault(norm, {"player_name": player_raw, "line": None, "over": None, "under": None})
        point = outcome.get("point")
        if point is not None:
            bucket["line"] = float(point)
        price = american_odds_str(outcome.get("price"))
        if side == "over":
            bucket["over"] = price
        else:
            bucket["under"] = price
    return grouped


def ingest_nba_player_prop_lines(
    db: Session,
    client: OddsApiClient,
    target_date: date,
    markets: Optional[Sequence[str]] = None,
    *,
    dry_run: bool = False,
    predictions_only: bool = False,
    bookmaker_priority: Sequence[str] = DEFAULT_BOOKMAKER_PRIORITY,
) -> IngestSummary:
    market_list = list(markets or DEFAULT_MARKETS)
    cache_date = target_date.isoformat()
    summary = IngestSummary()
    if dry_run:
        logger.info("Dry run: skipping Odds API HTTP calls")
        return summary

    events, _ = client.fetch_nba_events(cache_date)
    team_lookup = _build_team_lookup(db)
    prediction_game_ids = _game_ids_with_predictions(db, target_date) if predictions_only else None

    dated_events: List[Tuple[Dict[str, Any], Game]] = []
    for event in events:
        if event.get("sport_key") and event.get("sport_key") != NBA_SPORT_KEY:
            continue
        commence_date = event_commence_central_date(event)
        if commence_date != target_date:
            continue
        summary.events_considered += 1
        game = find_game_for_event(db, event, target_date, team_lookup)
        if not game:
            summary.skipped_no_game += 1
            summary.unmatched_games.append(str(event.get("id")))
            continue
        if prediction_game_ids is not None and game.game_id not in prediction_game_ids:
            summary.skipped_predictions_filter += 1
            continue
        dated_events.append((event, game))

    if not dated_events:
        logger.info("No NBA odds events matched for %s", target_date)
        return summary

    line_service = BettingLineService(db)
    bookmakers_param = list(bookmaker_priority)

    for event, game in dated_events:
        event_id = str(event.get("id"))
        odds_payload, _ = client.fetch_event_odds(event_id, market_list, bookmakers_param, cache_date)
        summary.events_fetched += 1
        if not odds_payload:
            continue

        markets_outcomes = _pick_market_outcomes(odds_payload, market_list, bookmaker_priority)
        if not markets_outcomes:
            logger.warning("No bookmaker lines for event %s", event_id)
            continue

        roster = _players_for_game_teams(db, game.home_team_id, game.away_team_id)

        for market_key, (book_used, outcomes) in markets_outcomes.items():
            stat_type = MARKET_TO_STAT_TYPE.get(market_key)
            if not stat_type:
                continue
            sportsbook = BOOKMAKER_DISPLAY.get(book_used, book_used.title())
            props = _parse_prop_outcomes(outcomes)
            for _norm, prop in props.items():
                player_name = prop.get("player_name") or ""
                player_id = match_player_id(player_name, roster)
                if not player_id:
                    summary.unmatched_players.add(player_name)
                    logger.warning("Unmatched player name from odds: %s (game %s)", player_name, game.game_id)
                    continue
                line_val = prop.get("line")
                over_odds = prop.get("over")
                under_odds = prop.get("under")
                if line_val is None or not over_odds:
                    continue
                if dry_run:
                    summary.lines_dry_run += 1
                    logger.info(
                        "DRY RUN line: %s %s %.1f over %s (%s)",
                        player_name,
                        stat_type,
                        line_val,
                        over_odds,
                        sportsbook,
                    )
                    continue
                line_service.add_betting_line(
                    game_id=game.game_id,
                    player_id=player_id,
                    stat_type=stat_type,
                    over_line=float(line_val),
                    over_odds=over_odds,
                    under_odds=under_odds or over_odds,
                    sportsbook=sportsbook,
                    source="api",
                )
                summary.lines_upserted += 1

    if summary.unmatched_players:
        logger.info(
            "Unmatched player names (%d): %s",
            len(summary.unmatched_players),
            ", ".join(sorted(summary.unmatched_players)[:20]),
        )
    return summary


def parse_markets_arg(raw: Optional[str]) -> List[str]:
    if not raw:
        return list(DEFAULT_MARKETS)
    keys = [p.strip() for p in raw.split(",") if p.strip()]
    unknown = [k for k in keys if k not in MARKET_TO_STAT_TYPE]
    if unknown:
        raise ValueError(f"Unknown markets: {', '.join(unknown)}")
    return keys


def central_today() -> date:
    return datetime.now(CENTRAL).date()
