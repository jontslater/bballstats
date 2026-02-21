"""
Baseball Reference Scraper

Scrapes box scores, game data, and schedules from baseball-reference.com for MLB.
"""
import time
import re
from typing import List, Dict, Optional
from datetime import date
import requests
from bs4 import BeautifulSoup


class BaseballReferenceScraper:
    """Scraper for baseball-reference.com"""

    BASE_URL = "https://www.baseball-reference.com"

    # Standard MLB team abbreviations (Baseball Reference uses 3-letter codes)
    TEAM_ABBREV_MAP = {
        'NYY': 'NYY', 'BOS': 'BOS', 'TBR': 'TBR', 'TOR': 'TOR', 'BAL': 'BAL',
        'CLE': 'CLE', 'CWS': 'CWS', 'DET': 'DET', 'KCR': 'KCR', 'MIN': 'MIN',
        'HOU': 'HOU', 'LAA': 'LAA', 'OAK': 'OAK', 'SEA': 'SEA', 'TEX': 'TEX',
        'ATL': 'ATL', 'MIA': 'MIA', 'NYM': 'NYM', 'PHI': 'PHI', 'WSN': 'WSN',
        'CHC': 'CHC', 'CIN': 'CIN', 'MIL': 'MIL', 'PIT': 'PIT', 'STL': 'STL',
        'ARI': 'ARI', 'COL': 'COL', 'LAD': 'LAD', 'SDP': 'SDP', 'SFG': 'SFG',
        'TB': 'TBR', 'KC': 'KCR', 'SD': 'SDP', 'SF': 'SFG', 'WSH': 'WSN', 'LA': 'LAD',
    }

    def __init__(self, delay: float = 5.0):
        self.delay = delay
        self.last_request_time = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _rate_limit(self):
        current_time = time.time()
        if current_time - self.last_request_time < self.delay:
            time.sleep(self.delay - (current_time - self.last_request_time))
        self.last_request_time = time.time()

    def _get_page(self, url: str, retries: int = 5) -> Optional[BeautifulSoup]:
        self._rate_limit()
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=15)
                if response.status_code == 429:
                    # Baseball Reference: wait longer - 2min, 5min, 10min, 15min, 20min
                    wait = [120, 300, 600, 900, 1200][min(attempt, 4)]
                    print(f"  Rate limited (429). Waiting {wait}s ({wait//60} min) before retry {attempt + 1}/{retries}...")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return BeautifulSoup(response.content, 'html.parser')
            except Exception as e:
                if attempt < retries - 1:
                    wait = 30 if '429' in str(e) else 5
                    time.sleep(wait)
                else:
                    print(f"  Error fetching {url}: {e}")
                    return None
        return None

    def get_games_for_date(self, game_date: date) -> List[Dict]:
        """
        Get all games for a specific date.
        URL: /boxes/index.fcgi?date=YYYY-MM-DD
        """
        date_str = game_date.strftime('%Y-%m-%d')
        url = f"{self.BASE_URL}/boxes/index.fcgi?date={date_str}"
        soup = self._get_page(url)
        if not soup:
            return []

        games = []
        # Find game summaries - Baseball Ref uses .game_summary or similar
        game_divs = soup.find_all('div', class_=re.compile(r'game_summary|summary'))
        if not game_divs:
            # Alternative: find links to box scores
            box_links = soup.find_all('a', href=re.compile(r'/boxes/[A-Z]+/[A-Z]+\d+\.shtml'))
            seen = set()
            for link in box_links:
                href = link.get('href', '')
                match = re.search(r'/boxes/([A-Z]+)/([A-Z]+)(\d+)\.shtml', href)
                if match:
                    away_abbr, home_abbr, game_id = match.groups()
                    key = (away_abbr, home_abbr, game_id)
                    if key not in seen:
                        seen.add(key)
                        games.append({
                            'away_team': self.TEAM_ABBREV_MAP.get(away_abbr, away_abbr),
                            'home_team': self.TEAM_ABBREV_MAP.get(home_abbr, home_abbr),
                            'game_date': game_date,
                            'box_score_id': f"{home_abbr}{game_id}",
                            'box_score_url': f"/boxes/{away_abbr}/{home_abbr}{game_id}.shtml"
                        })
            return games

        for div in game_divs:
            try:
                links = div.find_all('a', href=re.compile(r'/boxes/'))
                if links:
                    href = links[0]['href']
                    match = re.search(r'/boxes/([A-Z]+)/([A-Z]+)(\d+)\.shtml', href)
                    if match:
                        away_abbr, home_abbr, gid = match.groups()
                        games.append({
                            'away_team': self.TEAM_ABBREV_MAP.get(away_abbr, away_abbr),
                            'home_team': self.TEAM_ABBREV_MAP.get(home_abbr, home_abbr),
                            'game_date': game_date,
                            'box_score_id': f"{home_abbr}{gid}",
                            'box_score_url': href
                        })
            except Exception:
                continue
        return games

    def get_box_score(self, box_score_url: str, game_date: date, away_abbr: str, home_abbr: str) -> Optional[Dict]:
        """
        Get batting and pitching stats from a box score.
        """
        url = f"{self.BASE_URL}{box_score_url}" if box_score_url.startswith('/') else box_score_url
        soup = self._get_page(url)
        if not soup:
            return None

        player_stats = []

        # Batting tables - id pattern: team_abbrev_batting (e.g., NYYbatting)
        batting_tables = soup.find_all('table', id=re.compile(r'[a-z]{2,3}batting'))
        for table in batting_tables:
            tbody = table.find('tbody')
            if not tbody:
                continue
            team_abbr = table.get('id', '')[:3].upper() if table.get('id') else None
            for row in tbody.find_all('tr'):
                if row.get('class') and 'thead' in ' '.join(row.get('class', [])):
                    continue
                try:
                    stat_row = self._parse_batting_row(row, team_abbr)
                    if stat_row:
                        player_stats.append(stat_row)
                except Exception as e:
                    continue

        # Pitching tables
        pitching_tables = soup.find_all('table', id=re.compile(r'[a-z]{2,3}pitching'))
        for table in pitching_tables:
            tbody = table.find('tbody')
            if not tbody:
                continue
            team_abbr = table.get('id', '')[:3].upper() if table.get('id') else None
            for row in tbody.find_all('tr'):
                if row.get('class') and 'thead' in ' '.join(row.get('class', [])):
                    continue
                try:
                    stat_row = self._parse_pitching_row(row, team_abbr)
                    if stat_row:
                        player_stats.append(stat_row)
                except Exception:
                    continue

        # Get scores
        linescore = soup.find('table', class_='linescore')
        away_score = home_score = None
        if linescore:
            rows = linescore.find_all('tr')
            if len(rows) >= 2:
                away_cells = rows[1].find_all('td', class_='right')
                if len(away_cells) >= 2:
                    try:
                        away_score = int(away_cells[-1].text)
                    except ValueError:
                        pass
            if len(rows) >= 3:
                home_cells = rows[2].find_all('td', class_='right')
                if len(home_cells) >= 2:
                    try:
                        home_score = int(home_cells[-1].text)
                    except ValueError:
                        pass

        return {
            'game_date': game_date,
            'away_team': away_abbr,
            'home_team': home_abbr,
            'away_score': away_score,
            'home_score': home_score,
            'player_stats': player_stats
        }

    def _parse_batting_row(self, row, team_abbr: Optional[str]) -> Optional[Dict]:
        """Parse a batting stat row. Uses data-stat attributes."""
        player_cell = row.find('th', {'data-stat': 'player'}) or row.find('th')
        if not player_cell:
            return None
        player_link = player_cell.find('a')
        player_name = (player_link.text if player_link else player_cell.text).strip()
        if not player_name or player_name in ('Player', 'Batting', 'Team Totals'):
            return None

        ab = self._get_stat_int(row, 'ab')
        if ab is None:
            return None

        h = self._get_stat_int(row, 'h') or 0
        double = self._get_stat_int(row, 'double') or self._get_stat_int(row, '2b') or 0
        triple = self._get_stat_int(row, 'triple') or self._get_stat_int(row, '3b') or 0
        hr = self._get_stat_int(row, 'hr') or 0
        rbi = self._get_stat_int(row, 'rbi') or 0
        pa = self._get_stat_int(row, 'pa') or ab

        # Total bases = 1B + 2*2B + 3*3B + 4*HR
        singles = h - double - triple - hr
        total_bases = singles + 2 * double + 3 * triple + 4 * hr

        return {
            'player_name': player_name,
            'team_abbreviation': team_abbr,
            'is_batter': True,
            'is_pitcher': False,
            'at_bats': ab,
            'plate_appearances': pa,
            'hits': h,
            'doubles': double,
            'triples': triple,
            'home_runs': hr,
            'total_bases': total_bases,
            'rbis': rbi,
        }

    def _parse_pitching_row(self, row, team_abbr: Optional[str]) -> Optional[Dict]:
        """Parse a pitching stat row."""
        player_cell = row.find('th', {'data-stat': 'player'}) or row.find('th')
        if not player_cell:
            return None
        player_link = player_cell.find('a')
        player_name = (player_link.text if player_link else player_cell.text).strip()
        if not player_name or player_name in ('Player', 'Pitching', 'Team Totals'):
            return None

        ip = self._get_stat_float(row, 'ip')
        if ip is None and not row.find('td', {'data-stat': 'ip'}):
            return None

        so = self._get_stat_int(row, 'so') or self._get_stat_int(row, 'strikeouts') or 0
        h_allowed = self._get_stat_int(row, 'h') or 0
        bb = self._get_stat_int(row, 'bb') or 0

        return {
            'player_name': player_name,
            'team_abbreviation': team_abbr,
            'is_batter': False,
            'is_pitcher': True,
            'innings_pitched': ip or 0.0,
            'strikeouts': so,
            'hits_allowed': h_allowed,
            'walks_allowed': bb,
        }

    def _get_stat_int(self, row, stat_name: str) -> Optional[int]:
        cell = row.find('td', {'data-stat': stat_name})
        if not cell:
            return None
        try:
            text = cell.text.strip()
            if not text:
                return None
            return int(text)
        except (ValueError, AttributeError):
            return None

    def _get_stat_float(self, row, stat_name: str) -> Optional[float]:
        cell = row.find('td', {'data-stat': stat_name})
        if not cell:
            return None
        try:
            text = cell.text.strip()
            if not text:
                return None
            # Handle "1.1" style IP
            return float(text)
        except (ValueError, AttributeError):
            return None
