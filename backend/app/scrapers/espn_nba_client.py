"""
ESPN public JSON client for NBA schedule, box scores, and injuries.

Primary data source for NBA ingestion (no API key). Designed to work when
stats.nba.com / nba_api is blocked.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

# ESPN team id -> our DB abbreviation (site.api.espn.com team ids)
ESPN_NBA_TEAM_ID_TO_ABBREV: Dict[str, str] = {
    "1": "ATL",
    "2": "BOS",
    "3": "NOP",
    "4": "CHI",
    "5": "CLE",
    "6": "DAL",
    "7": "DEN",
    "8": "DET",
    "9": "GSW",
    "10": "HOU",
    "11": "IND",
    "12": "LAC",
    "13": "LAL",
    "14": "MIA",
    "15": "MIL",
    "16": "MIN",
    "17": "BKN",
    "18": "NYK",
    "19": "ORL",
    "20": "PHI",
    "21": "PHX",
    "22": "POR",
    "23": "SAC",
    "24": "SAS",
    "25": "OKC",
    "26": "UTA",
    "27": "WAS",
    "28": "TOR",
    "29": "MEM",
    "30": "CHA",
}

# ESPN sometimes uses short codes in team.abbreviation
ESPN_NBA_ABBREV_NORMALIZE: Dict[str, str] = {
    "GS": "GSW",
    "NY": "NYK",
    "NO": "NOP",
    "SA": "SAS",
    "UTAH": "UTA",
    "UT": "UTA",
    "WSH": "WAS",
    "PHO": "PHX",
}


def normalize_nba_abbrev(raw: Optional[str], espn_team_id: Optional[str] = None) -> Optional[str]:
    if espn_team_id and str(espn_team_id) in ESPN_NBA_TEAM_ID_TO_ABBREV:
        return ESPN_NBA_TEAM_ID_TO_ABBREV[str(espn_team_id)]
    if not raw:
        return None
    up = raw.strip().upper()
    return ESPN_NBA_ABBREV_NORMALIZE.get(up, up)


def parse_minutes_value(raw: Any) -> int:
    if raw is None:
        return 0
    if isinstance(raw, (int, float)):
        return int(raw)
    s = str(raw).strip()
    if not s or s == "--":
        return 0
    if ":" in s:
        try:
            mins, secs = s.split(":", 1)
            return int(mins) + (1 if int(secs) >= 30 else 0)
        except (ValueError, TypeError):
            return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def parse_made_attempted(pair: str) -> Tuple[int, int]:
    if not pair or pair in ("--", "-"):
        return 0, 0
    m = re.match(r"^(\d+)-(\d+)$", str(pair).strip())
    if not m:
        return 0, 0
    return int(m.group(1)), int(m.group(2))


def _game_local_date(iso_utc: Optional[str], fallback: Optional[date] = None) -> Optional[date]:
    """Convert ESPN UTC timestamp to US Central calendar date (league reporting date)."""
    if not iso_utc:
        return fallback
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        central = dt.astimezone(ZoneInfo("America/Chicago"))
        return central.date()
    except (ValueError, TypeError):
        return fallback


class ESPNNBAClient:
    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"

    STATUS_MAP = {
        "STATUS_SCHEDULED": "scheduled",
        "STATUS_IN_PROGRESS": "in_progress",
        "STATUS_HALFTIME": "in_progress",
        "STATUS_END_PERIOD": "in_progress",
        "STATUS_FINAL": "finished",
        "STATUS_FINAL_OVERTIME": "finished",
        "STATUS_POSTPONED": "cancelled",
        "STATUS_CANCELED": "cancelled",
        "STATUS_CANCELLED": "cancelled",
    }

    def __init__(self, delay: float = 0.35):
        self.delay = delay
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.time()

    def _get_json(self, url: str, params: Optional[Dict] = None, retries: int = 4) -> Optional[Dict]:
        self._rate_limit()
        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=20)
                if resp.status_code == 403 and attempt < retries - 1:
                    time.sleep(4 * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException:
                if attempt < retries - 1:
                    time.sleep(2 * (2 ** attempt))
                else:
                    return None
        return None

    def get_scoreboard(
        self,
        dates: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> List[Dict]:
        """
        Fetch scoreboard events. `dates` is YYYYMMDD or YYYYMMDD-YYYYMMDD.
        When iterating single days, pass dates=game_date.strftime('%Y%m%d') and
        use that calendar date as game_date (US-oriented ESPN bucket).
        """
        params: Dict[str, str] = {}
        if dates:
            params["dates"] = dates
        elif date_from and date_to:
            params["dates"] = f"{date_from.strftime('%Y%m%d')}-{date_to.strftime('%Y%m%d')}"
        elif date_from:
            params["dates"] = date_from.strftime("%Y%m%d")

        data = self._get_json(f"{self.BASE_URL}/scoreboard", params=params or None)
        if not data:
            return []

        scoreboard_date = None
        if dates and len(dates) == 8 and dates.isdigit():
            scoreboard_date = datetime.strptime(dates, "%Y%m%d").date()

        games: List[Dict] = []
        for event in data.get("events", []):
            parsed = self._parse_scoreboard_event(event, scoreboard_date)
            if parsed:
                games.append(parsed)
        return games

    def _parse_scoreboard_event(self, event: Dict, scoreboard_date: Optional[date]) -> Optional[Dict]:
        try:
            espn_game_id = str(event.get("id", ""))
            if not espn_game_id:
                return None

            status_name = event.get("status", {}).get("type", {}).get("name", "")
            game_status = self.STATUS_MAP.get(status_name, "scheduled")

            competitions = event.get("competitions") or []
            if not competitions:
                return None
            comp = competitions[0]
            iso_date = comp.get("date") or event.get("date")
            game_date = scoreboard_date or _game_local_date(iso_date)

            home_abbrev = away_abbrev = None
            home_score = away_score = None
            for competitor in comp.get("competitors", []):
                team = competitor.get("team", {})
                tid = team.get("id")
                abbrev = normalize_nba_abbrev(team.get("abbreviation"), tid)
                score_raw = competitor.get("score")
                score = int(score_raw) if score_raw not in (None, "") and str(score_raw).isdigit() else None
                if not abbrev:
                    continue
                if competitor.get("homeAway") == "home":
                    home_abbrev = abbrev
                    home_score = score
                elif competitor.get("homeAway") == "away":
                    away_abbrev = abbrev
                    away_score = score

            if not home_abbrev or not away_abbrev or not game_date:
                return None
            if home_abbrev == away_abbrev:
                return None

            game_time = None
            if iso_date:
                try:
                    game_time = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    game_time = None

            return {
                "espn_game_id": espn_game_id,
                "game_date": game_date,
                "game_time": game_time,
                "home_team": home_abbrev,
                "away_team": away_abbrev,
                "home_score": home_score,
                "away_score": away_score,
                "status": game_status,
                "status_name": status_name,
            }
        except (KeyError, TypeError, ValueError):
            return None

    def get_summary(self, espn_game_id: str) -> Optional[Dict]:
        return self._get_json(f"{self.BASE_URL}/summary", params={"event": espn_game_id})

    def parse_box_score(self, summary: Dict, game_meta: Optional[Dict] = None) -> Optional[Dict]:
        """Parse ESPN summary JSON into normalized player/team stats."""
        if not summary:
            return None

        box = summary.get("boxscore") or {}
        player_groups = box.get("players") or []
        if not player_groups:
            return None

        header = summary.get("header") or {}
        comp = (header.get("competitions") or [{}])[0]
        home_abbrev = away_abbrev = None
        home_score = away_score = None
        for competitor in comp.get("competitors", []):
            team = competitor.get("team", {})
            abbrev = normalize_nba_abbrev(team.get("abbreviation"), team.get("id"))
            score_raw = competitor.get("score")
            score = int(score_raw) if score_raw not in (None, "") and str(score_raw).isdigit() else None
            if competitor.get("homeAway") == "home":
                home_abbrev = abbrev
                home_score = score
            elif competitor.get("homeAway") == "away":
                away_abbrev = abbrev
                away_score = score

        if game_meta:
            home_abbrev = home_abbrev or game_meta.get("home_team")
            away_abbrev = away_abbrev or game_meta.get("away_team")
            home_score = home_score if home_score is not None else game_meta.get("home_score")
            away_score = away_score if away_score is not None else game_meta.get("away_score")

        player_stats: List[Dict] = []
        for group in player_groups:
            team_info = group.get("team") or {}
            team_abbrev = normalize_nba_abbrev(team_info.get("abbreviation"), team_info.get("id"))
            for stat_block in group.get("statistics") or []:
                names = stat_block.get("names") or []
                for athlete_row in stat_block.get("athletes") or []:
                    athlete = athlete_row.get("athlete") or {}
                    if athlete_row.get("didNotPlay"):
                        continue
                    stats_list = athlete_row.get("stats") or []
                    if not stats_list:
                        continue
                    row = dict(zip(names, stats_list))
                    fgm, fga = parse_made_attempted(row.get("FG", "0-0"))
                    fg3m, fg3a = parse_made_attempted(row.get("3PT", "0-0"))
                    ftm, fta = parse_made_attempted(row.get("FT", "0-0"))
                    player_stats.append(
                        {
                            "espn_player_id": str(athlete.get("id", "")),
                            "player_name": athlete.get("displayName") or athlete.get("shortName") or "Unknown",
                            "team_abbreviation": team_abbrev,
                            "minutes_played": parse_minutes_value(row.get("MIN")),
                            "points": int(row.get("PTS") or 0),
                            "rebounds": int(row.get("REB") or 0),
                            "offensive_rebounds": int(row.get("OREB") or 0),
                            "defensive_rebounds": int(row.get("DREB") or 0),
                            "assists": int(row.get("AST") or 0),
                            "steals": int(row.get("STL") or 0),
                            "blocks": int(row.get("BLK") or 0),
                            "turnovers": int(row.get("TO") or 0),
                            "personal_fouls": int(row.get("PF") or 0),
                            "field_goals_made": fgm,
                            "field_goals_attempted": fga,
                            "three_pointers_made": fg3m,
                            "three_pointers_attempted": fg3a,
                            "free_throws_made": ftm,
                            "free_throws_attempted": fta,
                            "plus_minus": int(row.get("+/-") or row.get("PM") or 0),
                            "is_starter": bool(athlete_row.get("starter")),
                        }
                    )

        injuries = self.parse_injuries(summary)

        return {
            "home_team": home_abbrev,
            "away_team": away_abbrev,
            "home_score": home_score,
            "away_score": away_score,
            "player_stats": player_stats,
            "injuries": injuries,
        }

    def parse_injuries(self, summary: Dict) -> List[Dict]:
        out: List[Dict] = []
        for team_block in summary.get("injuries") or []:
            team = team_block.get("team") or {}
            team_abbrev = normalize_nba_abbrev(team.get("abbreviation"), team.get("id"))
            for inj in team_block.get("injuries") or []:
                athlete = inj.get("athlete") or {}
                raw_status = inj.get("status")
                if isinstance(raw_status, dict):
                    status = raw_status.get("description") or raw_status.get("name") or "Unknown"
                else:
                    status = raw_status or "Unknown"
                raw_type = inj.get("type")
                if isinstance(raw_type, dict):
                    injury_type = raw_type.get("description") or raw_type.get("name") or ""
                else:
                    injury_type = raw_type or inj.get("details", {}).get("type") or ""
                out.append(
                    {
                        "espn_player_id": str(athlete.get("id", "")),
                        "player_name": athlete.get("displayName") or "",
                        "team_abbreviation": team_abbrev,
                        "status": str(status),
                        "injury_type": str(injury_type),
                        "description": inj.get("longComment") or inj.get("shortComment") or "",
                    }
                )
        return out

    def get_games_for_date(self, game_date: date) -> List[Dict]:
        return self.get_scoreboard(dates=game_date.strftime("%Y%m%d"))

    def get_box_score_for_game(self, espn_game_id: str, game_meta: Optional[Dict] = None) -> Optional[Dict]:
        summary = self.get_summary(espn_game_id)
        if not summary:
            return None
        return self.parse_box_score(summary, game_meta=game_meta)
