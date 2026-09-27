"""
ESPN NFL API Client

Uses ESPN's public NFL API for schedule and game data.
This is a more reliable alternative to Pro Football Reference scraping.
"""
import requests
import time
from typing import List, Dict, Optional
from datetime import date, datetime, timedelta


class ESPNNFLClient:
    """Client for ESPN NFL API."""
    
    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
    
    # ESPN team ID to abbreviation mapping
    TEAM_ABBREV_MAP = {
        '1': 'ATL', '2': 'BUF', '3': 'CHI', '4': 'CIN', '5': 'CLE',
        '6': 'DAL', '7': 'DEN', '8': 'DET', '9': 'GB', '10': 'TEN',
        '11': 'IND', '12': 'KC', '13': 'LV', '14': 'LAR', '15': 'MIA',
        '16': 'MIN', '17': 'NE', '18': 'NO', '19': 'NYG', '20': 'NYJ',
        '21': 'PHI', '22': 'ARI', '23': 'PIT', '24': 'LAC', '25': 'SF',
        '26': 'SEA', '27': 'TB', '28': 'WAS', '29': 'CAR', '30': 'JAX',
        '33': 'BAL', '34': 'HOU'
    }
    
    def __init__(self, delay: float = 0.5):
        """
        Initialize ESPN NFL client.
        
        Args:
            delay: Seconds to wait between requests (ESPN is more lenient than PFR)
        """
        self.delay = delay
        self.last_request_time = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9'
        })
    
    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        
        self.last_request_time = time.time()
    
    def _get_json(self, url: str, retries: int = 3) -> Optional[Dict]:
        """Fetch JSON data with exponential backoff."""
        self._rate_limit()
        
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                if response.status_code == 403:
                    print(f"  ⚠️  HTTP 403 from ESPN API")
                    if attempt < retries - 1:
                        wait_time = 4 * (2 ** attempt)
                        print(f"  ⏳ Waiting {wait_time}s before retry {attempt + 1}/{retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"  ❌ ESPN API access blocked after {retries} retries")
                        return None
                elif attempt < retries - 1:
                    wait_time = 2 * (2 ** attempt)
                    time.sleep(wait_time)
                else:
                    print(f"  ❌ HTTP error from {url}: {e}")
                    return None
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2)
                else:
                    print(f"  ❌ Error fetching {url}: {e}")
                    return None
        
        return None
    
    def get_team_abbrev(self, espn_team_id: str) -> Optional[str]:
        """Convert ESPN team ID to our abbreviation."""
        return self.TEAM_ABBREV_MAP.get(str(espn_team_id))
    
    def get_scoreboard(self, season_year: int = None, week: int = None, dates: str = None) -> List[Dict]:
        """
        Get NFL scoreboard/schedule from ESPN.
        
        Args:
            season_year: Season year (e.g., 2024)
            week: Week number (1-22)
            dates: Date string YYYYMMDD or date range YYYYMMDD-YYYYMMDD
        
        Returns:
            List of game dictionaries
        """
        url = f"{self.BASE_URL}/scoreboard"
        params = {}
        
        if season_year:
            params['seasontype'] = 2  # Regular season (2) or playoffs (3)
        if week:
            params['week'] = week
        if dates:
            params['dates'] = dates
        
        if params:
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            url = f"{url}?{query_string}"
        
        data = self._get_json(url)
        if not data:
            return []
        
        games = []
        events = data.get('events', [])
        
        for event in events:
            try:
                # Get game info
                game_id = event.get('id')
                game_date_str = event.get('date')  # ISO format
                game_status = event.get('status', {}).get('type', {}).get('name', 'scheduled')
                
                # Parse date
                if game_date_str:
                    game_date = datetime.fromisoformat(game_date_str.replace('Z', '+00:00')).date()
                else:
                    continue
                
                # Get teams
                competitions = event.get('competitions', [])
                if not competitions:
                    continue
                
                competition = competitions[0]
                competitors = competition.get('competitors', [])
                
                if len(competitors) < 2:
                    continue
                
                # ESPN format: competitors[0] is usually away, competitors[1] is home
                # But check homeAway field to be sure
                home_team = None
                away_team = None
                home_score = None
                away_score = None
                
                for comp in competitors:
                    team = comp.get('team', {})
                    team_id = team.get('id')
                    team_abbrev = self.get_team_abbrev(team_id)
                    
                    if not team_abbrev:
                        continue
                    
                    is_home = comp.get('homeAway') == 'home'
                    score = comp.get('score')
                    
                    if is_home:
                        home_team = team_abbrev
                        home_score = int(score) if score and score.isdigit() else None
                    else:
                        away_team = team_abbrev
                        away_score = int(score) if score and score.isdigit() else None
                
                if not home_team or not away_team:
                    continue
                
                games.append({
                    'espn_game_id': game_id,
                    'game_date': game_date,
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_score': home_score,
                    'away_score': away_score,
                    'status': 'finished' if game_status in ['STATUS_FINAL', 'Final'] else 'scheduled'
                })
                
            except Exception as e:
                print(f"  ⚠️  Error parsing game: {e}")
                continue
        
        return games
    
    def get_games_for_date(self, game_date: date) -> List[Dict]:
        """
        Get all games for a specific date.
        
        Args:
            game_date: Date to get games for
        
        Returns:
            List of game dictionaries
        """
        # ESPN dates format: YYYYMMDD
        date_str = game_date.strftime('%Y%m%d')
        return self.get_scoreboard(dates=date_str)
    
    def get_games_for_week(self, season_year: int, week: int) -> List[Dict]:
        """
        Get all games for a specific week.
        
        Args:
            season_year: Season year (e.g., 2024)
            week: Week number (1-22)
        
        Returns:
            List of game dictionaries
        """
        return self.get_scoreboard(season_year=season_year, week=week)
    
    def get_season_schedule(self, season_year: int) -> List[Dict]:
        """
        Get full season schedule.
        
        Args:
            season_year: Season year (e.g., 2024)
        
        Returns:
            List of game dictionaries
        """
        all_games = []
        
        # NFL: 18 weeks regular season + 4 weeks playoffs
        for week in range(1, 23):
            print(f"  Fetching Week {week}...")
            week_games = self.get_games_for_week(season_year, week)
            all_games.extend(week_games)
            
            if not week_games:
                print(f"    No games found for Week {week}")
        
        return all_games
