"""
Pro Football Reference Scraper

Scrapes box scores, game data, schedules, and player stats from 
pro-football-reference.com for NFL data collection.
"""
import time
import re
from typing import List, Dict, Optional
from datetime import date, datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup


class ProFootballReferenceScraper:
    """Scraper for pro-football-reference.com"""
    
    BASE_URL = "https://www.pro-football-reference.com"
    
    # Team abbreviation mapping (Pro Football Reference uses standard abbreviations)
    TEAM_ABBREV_MAP = {
        'ARI': 'ARI', 'ATL': 'ATL', 'BAL': 'BAL', 'BUF': 'BUF',
        'CAR': 'CAR', 'CHI': 'CHI', 'CIN': 'CIN', 'CLE': 'CLE',
        'DAL': 'DAL', 'DEN': 'DEN', 'DET': 'DET', 'GB': 'GNB',  # Green Bay (GNB in PFR)
        'GNB': 'GNB', 'HOU': 'HOU', 'IND': 'IND', 'JAX': 'JAX',
        'KC': 'KAN', 'KAN': 'KAN',  # Kansas City
        'LV': 'RAI', 'RAI': 'RAI',  # Las Vegas Raiders (RAI in PFR)
        'LAC': 'LAC', 'LAR': 'LAR', 'MIA': 'MIA', 'MIN': 'MIN',
        'NE': 'NWE', 'NWE': 'NWE',  # New England
        'NO': 'NOR', 'NOR': 'NOR',  # New Orleans
        'NYG': 'NYG', 'NYJ': 'NYJ', 'PHI': 'PHI', 'PIT': 'PIT',
        'SF': 'SFO', 'SFO': 'SFO',  # San Francisco
        'SEA': 'SEA', 'TB': 'TAM', 'TAM': 'TAM',  # Tampa Bay
        'TEN': 'TEN', 'WAS': 'WAS'
    }
    
    def __init__(self, delay: float = 2.0):
        """
        Initialize scraper.

        Args:
            delay: Seconds to wait between requests (PFR recommends 2-3 seconds)
        """
        self.delay = delay
        self.last_request_time = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        # Disable SSL verification to work around certificate issues
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.delay:
            sleep_time = self.delay - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _get_page(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse a page."""
        self._rate_limit()
        
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                return BeautifulSoup(response.content, 'html.parser')
            except Exception as e:
                if attempt < retries - 1:
                    print(f"  ⚠️  Retry {attempt + 1}/{retries} for {url}")
                    time.sleep(2)
                else:
                    print(f"  ❌ Error fetching {url}: {e}")
                    return None
        
        return None
    
    def get_games_for_date(self, game_date: date) -> List[Dict]:
        """
        Get all games for a specific date.
        
        Args:
            game_date: Date to get games for
        
        Returns:
            List of game dictionaries with basic info
        """
        # Pro Football Reference uses index.htm with date params for game listings
        # URL format: /boxscores/index.htm?year=YYYY&month=M&day=D
        year = game_date.year
        month = game_date.month
        day = game_date.day
        
        # Try the index page with date params
        url = f"{self.BASE_URL}/boxscores/index.htm?year={year}&month={month}&day={day}"
        
        soup = self._get_page(url)
        if not soup:
            print(f"    ⚠️  Could not fetch games page for {game_date}")
            return []
        
        games = []
        
        # Find all game boxes - PFR has divs with class "game_summary"
        game_summaries = soup.find_all('div', class_='game_summary')
        
        for game_summary in game_summaries:
            try:
                # Get team names and scores
                away_team_elem = game_summary.find('tr', class_='loser') or game_summary.find('tr', class_='winner')
                home_team_elem = game_summary.find_all('tr', class_=re.compile('^(winner|loser)$'))
                
                if len(home_team_elem) < 2:
                    continue
                
                away_row = away_team_elem
                home_row = home_team_elem[1] if home_team_elem[0] == away_row else home_team_elem[0]
                
                away_team_abbr = away_row.find('a')['href'].split('/')[-2].upper()
                home_team_abbr = home_row.find('a')['href'].split('/')[-2].upper()
                
                away_score_elem = away_row.find('td', class_='right')
                home_score_elem = home_row.find('td', class_='right')
                
                away_score = int(away_score_elem.text) if away_score_elem and away_score_elem.text.isdigit() else None
                home_score = int(home_score_elem.text) if home_score_elem and home_score_elem.text.isdigit() else None
                
                # Get game link
                box_score_link = game_summary.find('a', href=re.compile(r'/boxscores/\d+'))
                game_id = None
                if box_score_link:
                    game_id = box_score_link['href'].split('/')[-1].replace('.htm', '')
                
                games.append({
                    'away_team': away_team_abbr,
                    'home_team': home_team_abbr,
                    'away_score': away_score,
                    'home_score': home_score,
                    'game_date': game_date,
                    'game_id': game_id
                })
            except Exception as e:
                print(f"    ⚠️  Error parsing game: {e}")
                continue
        
        return games
    
    def get_box_score(self, game_id: str, game_date: date) -> Optional[Dict]:
        """
        Get detailed box score for a game.
        
        Args:
            game_id: Game ID (e.g., "202312240kan" for KC game on Dec 24, 2023)
            game_date: Game date
        
        Returns:
            Dictionary with player stats and game info
        """
        url = f"{self.BASE_URL}/boxscores/{game_id}.htm"
        soup = self._get_page(url)
        
        if not soup:
            return None
        
        try:
            # Get team abbreviations from URL or page
            away_team_abbr = None
            home_team_abbr = None
            
            # Try to get from game_id format: YYYYMMDDaaa.htm (where aaa is home team)
            if len(game_id) >= 11:
                home_team_abbr = game_id[-3:].upper()
            
            # Get scores
            scores = soup.find_all('div', class_='score')
            away_score = None
            home_score = None
            
            if len(scores) >= 2:
                try:
                    away_score = int(scores[0].text.strip())
                    home_score = int(scores[1].text.strip())
                except ValueError:
                    pass
            
            # Get player stats
            player_stats = []
            
            # Find all stat tables (offense, defense)
            stat_tables = soup.find_all('table', id=re.compile(r'(player_offense|player_defense)'))
            
            for table in stat_tables:
                is_offense = 'offense' in table.get('id', '')
                
                # Find tbody
                tbody = table.find('tbody')
                if not tbody:
                    continue
                
                rows = tbody.find_all('tr')
                for row in rows:
                    # Skip header rows
                    if row.get('class') and 'thead' in row.get('class'):
                        continue
                    
                    try:
                        # Get player name
                        player_cell = row.find('th', {'data-stat': 'player'})
                        if not player_cell:
                            continue
                        
                        player_link = player_cell.find('a')
                        player_name = player_link.text if player_link else player_cell.text.strip()
                        
                        if not player_name or player_name == 'Player':
                            continue
                        
                        # Get team abbreviation
                        team_cell = row.find('td', {'data-stat': 'team'})
                        team_abbr = team_cell.text.strip() if team_cell else None
                        
                        # Get position
                        pos_cell = row.find('td', {'data-stat': 'pos'})
                        position = pos_cell.text.strip() if pos_cell else None
                        
                        # Get stats based on offense/defense
                        stat_dict = {
                            'player_name': player_name,
                            'team_abbreviation': team_abbr,
                            'position': position
                        }
                        
                        if is_offense:
                            # Offensive stats
                            stat_dict.update({
                                'passing_completions': self._get_stat_int(row, 'pass_cmp'),
                                'passing_attempts': self._get_stat_int(row, 'pass_att'),
                                'passing_yards': self._get_stat_int(row, 'pass_yds'),
                                'passing_tds': self._get_stat_int(row, 'pass_td'),
                                'interceptions': self._get_stat_int(row, 'pass_int'),
                                'rushing_attempts': self._get_stat_int(row, 'rush_att'),
                                'rushing_yards': self._get_stat_int(row, 'rush_yds'),
                                'rushing_tds': self._get_stat_int(row, 'rush_td'),
                                'receptions': self._get_stat_int(row, 'rec'),
                                'receiving_yards': self._get_stat_int(row, 'rec_yds'),
                                'receiving_tds': self._get_stat_int(row, 'rec_td'),
                                'targets': self._get_stat_int(row, 'targets'),
                                'fumbles': self._get_stat_int(row, 'fumbles'),
                                'fumbles_lost': self._get_stat_int(row, 'fumbles_lost'),
                            })
                        else:
                            # Defensive stats (if we want to track them)
                            pass
                        
                        player_stats.append(stat_dict)
                    except Exception as e:
                        print(f"    ⚠️  Error parsing player row: {e}")
                        continue
            
            return {
                'game_id': game_id,
                'game_date': game_date,
                'away_team': away_team_abbr,
                'home_team': home_team_abbr,
                'away_score': away_score,
                'home_score': home_score,
                'player_stats': player_stats
            }
        except Exception as e:
            print(f"  ❌ Error parsing box score: {e}")
            return None
    
    def _get_stat_int(self, row, stat_name: str) -> Optional[int]:
        """Helper to extract integer stat from a table row."""
        cell = row.find('td', {'data-stat': stat_name})
        if not cell:
            return None
        try:
            text = cell.text.strip()
            # Handle empty strings or non-numeric
            if not text or text == '':
                return None
            return int(text)
        except (ValueError, AttributeError):
            return None
    
    def get_weekly_schedule(self, year: int, week: int) -> List[Dict]:
        """
        Get schedule for a specific week.
        
        Args:
            year: Season year (e.g., 2023)
            week: Week number (1-18 for regular season, 19+ for playoffs)
        
        Returns:
            List of game dictionaries
        """
        url = f"{self.BASE_URL}/years/{year}/week_{week}.htm"
        soup = self._get_page(url)
        
        if not soup:
            return []
        
        games = []
        # Similar parsing logic to get_games_for_date
        # Implementation similar to above...
        
        return games

