"""
MLB Stats API Client - Wrapper around MLB-StatsAPI package.

Uses official MLB Stats API (statsapi.mlb.com) - no rate limits like Baseball Reference.
Provides schedule and box score data for MLB games.
"""
import time
from typing import List, Dict, Optional, Any
from datetime import date, datetime


# MLB API team ID -> our abbreviation (from seed_mlb_teams)
MLB_TEAM_ID_TO_ABBREV = {
    108: 'LAA', 109: 'ARI', 110: 'BAL', 111: 'BOS', 112: 'CHC', 113: 'CIN',
    114: 'CLE', 115: 'COL', 116: 'DET', 117: 'HOU', 118: 'KCR', 119: 'LAD',
    120: 'WSN', 121: 'NYM', 133: 'OAK', 134: 'PIT', 135: 'SDP', 136: 'SEA',
    137: 'SFG', 138: 'STL', 139: 'TBR', 140: 'TEX', 141: 'TOR', 142: 'MIN',
    143: 'PHI', 144: 'ATL', 145: 'CWS', 146: 'MIA', 147: 'NYY', 158: 'MIL',
}


class MLBAPIClient:
    """Client for MLB Stats API - schedule and box scores."""

    def __init__(self, delay: float = 0.5):
        """
        Args:
            delay: Seconds between API calls (API is lenient, but be respectful)
        """
        self.delay = delay
        self.last_call_time = 0

    def _rate_limit(self):
        current = time.time()
        elapsed = current - self.last_call_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_call_time = time.time()

    def _ensure_import(self):
        try:
            import statsapi
            return statsapi
        except ImportError:
            raise ImportError(
                "MLB-StatsAPI not installed. Run: pip install MLB-StatsAPI"
            )

    def get_schedule(
        self,
        start_date: date = None,
        end_date: date = None,
        game_date: date = None
    ) -> List[Dict]:
        """
        Get MLB games for a date or date range.

        Calls statsapi.schedule() with no gameType filter so the Stats API
        returns regular season (R) and postseason series (F/D/L/W). Passing
        gameType=R would drop playoff games; gameTypes=P is not an umbrella
        (it returns 0 rows on statsapi.mlb.com).

        Returns list of games with game_id, game_type, home/away info, scores, status.
        """
        self._rate_limit()
        statsapi = self._ensure_import()

        if game_date:
            start_dt = end_dt = game_date.strftime('%m/%d/%Y')
        elif start_date and end_date:
            start_dt = start_date.strftime('%m/%d/%Y')
            end_dt = end_date.strftime('%m/%d/%Y')
        else:
            start_dt = end_dt = date.today().strftime('%m/%d/%Y')

        # Do not pass game_type/gameTypes — unfiltered schedule includes postseason.
        # Let exceptions propagate: an empty list means "no games", not "API failed".
        # Schedule reconcile must not treat a failed fetch as "drop every game".
        games = statsapi.schedule(
            start_date=start_dt,
            end_date=end_dt,
            sportId=1  # MLB
        )
        return games if games else []

    def get_box_score_data(self, game_id: int) -> Optional[Dict]:
        """
        Get raw box score data for a game.
        Returns dict with batting, pitching, team info.
        """
        self._rate_limit()
        statsapi = self._ensure_import()

        try:
            data = statsapi.boxscore_data(game_id)
            return data
        except Exception as e:
            print(f"  MLB API boxscore error for game {game_id}: {e}")
            return None

    def get_team_abbrev(self, mlb_team_id: int) -> Optional[str]:
        """Map MLB API team ID to our abbreviation."""
        return MLB_TEAM_ID_TO_ABBREV.get(mlb_team_id)

    def parse_box_score_for_db(
        self,
        box_data: Dict,
        home_abbrev: str,
        away_abbrev: str
    ) -> Dict:
        """
        Parse MLB-StatsAPI boxscore_data into our PlayerGameStat format.
        boxscore_data returns: awayBatters, homeBatters, awayPitchers, homePitchers,
        teamInfo, awayBattingTotals (teamStats), etc.
        """
        result = {
            'away_score': None,
            'home_score': None,
            'player_stats': []
        }

        # Get scores from batting totals (statsapi format)
        try:
            away_totals = box_data.get('awayBattingTotals', {})
            home_totals = box_data.get('homeBattingTotals', {})
            if isinstance(away_totals, dict):
                result['away_score'] = self._safe_int(away_totals.get('r'))
            if isinstance(home_totals, dict):
                result['home_score'] = self._safe_int(home_totals.get('r'))
        except Exception:
            pass

        # Batters - awayBatters and homeBatters (skip header row 0 and Totals at end)
        for batters_list, abbrev in [
            (box_data.get('awayBatters', []), away_abbrev),
            (box_data.get('homeBatters', []), home_abbrev)
        ]:
            if not isinstance(batters_list, list):
                continue
            for item in batters_list:
                if not isinstance(item, dict) or not item.get('name') or item.get('name') == 'Totals':
                    continue
                if 'Batters' in str(item.get('name', '')):  # Header row
                    continue
                s = self._parse_statsapi_batter(item, abbrev)
                if s and s.get('at_bats') is not None:
                    result['player_stats'].append(s)

        # Pitchers
        for pitchers_list, abbrev in [
            (box_data.get('awayPitchers', []), away_abbrev),
            (box_data.get('homePitchers', []), home_abbrev)
        ]:
            if not isinstance(pitchers_list, list):
                continue
            for item in pitchers_list:
                if not isinstance(item, dict) or not item.get('name') or item.get('name') == 'Totals':
                    continue
                if 'Pitchers' in str(item.get('name', '')):
                    continue
                s = self._parse_statsapi_pitcher(item, abbrev)
                if s:
                    result['player_stats'].append(s)

        return result

    def _parse_statsapi_batter(self, item: Dict, team_abbrev: str) -> Optional[Dict]:
        """Parse statsapi awayBatters/homeBatters item (values are strings)."""
        name = item.get('name', '').strip()
        if not name:
            return None
        ab = self._safe_int(item.get('ab'))
        if ab is None or ab == 0:
            return None  # Need at_bats for batters
        h = self._safe_int(item.get('h')) or 0
        double = self._safe_int(item.get('doubles')) or 0
        triple = self._safe_int(item.get('triples')) or 0
        hr = self._safe_int(item.get('hr')) or 0
        rbi = self._safe_int(item.get('rbi')) or 0
        singles = max(0, h - double - triple - hr)
        total_bases = singles + 2 * double + 3 * triple + 4 * hr

        return {
            'player_name': name,
            'team_abbreviation': team_abbrev,
            'is_batter': True,
            'is_pitcher': False,
            'at_bats': ab,
            'plate_appearances': ab,  # statsapi may not have PA in batter line
            'hits': h,
            'doubles': double,
            'triples': triple,
            'home_runs': hr,
            'total_bases': total_bases,
            'rbis': rbi,
        }

    def _parse_statsapi_pitcher(self, item: Dict, team_abbrev: str) -> Optional[Dict]:
        """Parse statsapi awayPitchers/homePitchers item."""
        name = item.get('name', '').strip()
        if not name:
            return None
        ip = self._safe_float(item.get('ip'))
        so = self._safe_int(item.get('k')) or 0
        h_allowed = self._safe_int(item.get('h')) or 0
        bb = self._safe_int(item.get('bb')) or 0
        if ip is None and so == 0 and h_allowed == 0:
            return None
        return {
            'player_name': name,
            'team_abbreviation': team_abbrev,
            'is_batter': False,
            'is_pitcher': True,
            'innings_pitched': ip if ip is not None else 0.0,
            'strikeouts': so,
            'hits_allowed': h_allowed,
            'walks_allowed': bb,
        }

    def _safe_int(self, v) -> Optional[int]:
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    def _safe_float(self, v) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None
