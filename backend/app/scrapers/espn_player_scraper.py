"""
ESPN Player Scraper

Scrapes player data from ESPN NBA team rosters to avoid NBA API rate limits.
"""
import requests
from bs4 import BeautifulSoup
import time
import re
from typing import List, Dict, Optional
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.player import Player
from app.models.team import Team


class ESPNPlayerScraper:
    """Scrape player data from ESPN NBA team rosters."""
    
    # ESPN team name mappings to our team abbreviations
    ESPN_TEAM_ABBREV_MAP = {
        'atl': 'ATL', 'bkn': 'BKN', 'bos': 'BOS', 'cha': 'CHA', 'chi': 'CHI',
        'cle': 'CLE', 'dal': 'DAL', 'den': 'DEN', 'det': 'DET', 'gs': 'GSW',
        'hou': 'HOU', 'ind': 'IND', 'lac': 'LAC', 'lal': 'LAL', 'mem': 'MEM',
        'mia': 'MIA', 'mil': 'MIL', 'min': 'MIN', 'no': 'NOP', 'ny': 'NYK',
        'okc': 'OKC', 'orl': 'ORL', 'phi': 'PHI', 'phx': 'PHX', 'por': 'POR',
        'sac': 'SAC', 'sa': 'SAS', 'tor': 'TOR', 'utah': 'UTA', 'wsh': 'WAS'
    }
    
    def __init__(self, db_session: Session = None, delay: float = 1.5):
        """
        Initialize ESPN player scraper.
        
        Args:
            db_session: Database session (optional)
            delay: Seconds to wait between requests (default: 1.5)
        """
        self.db = db_session if db_session else SessionLocal()
        self.delay = delay
        self.last_request_time = 0
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        
        self.last_request_time = time.time()
    
    def _get_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a web page."""
        self._rate_limit()
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            print(f"    ⚠️  Error fetching {url}: {e}")
            return None
    
    def get_all_teams(self) -> List[Team]:
        """Get all NBA teams from database."""
        return self.db.query(Team).filter(Team.sport == 'NBA').all()
    
    def scrape_team_roster(self, team_abbrev: str) -> List[Dict]:
        """
        Scrape player roster from ESPN for a specific team.
        
        Args:
            team_abbrev: Team abbreviation (e.g., 'DAL', 'LAL')
        
        Returns:
            List of player dictionaries
        """
        # Map our team abbreviation to ESPN team name
        espn_team_name = None
        for espn_key, abbrev in self.ESPN_TEAM_ABBREV_MAP.items():
            if abbrev == team_abbrev:
                espn_team_name = espn_key
                break
        
        if not espn_team_name:
            print(f"    ⚠️  Unknown ESPN team name for {team_abbrev}")
            return []
        
        # ESPN roster URL format: https://www.espn.com/nba/team/roster/_/name/dal/dallas-mavericks
        # We need to construct the full team name for the URL
        team_name_map = {
            'atl': 'atlanta-hawks', 'bkn': 'brooklyn-nets', 'bos': 'boston-celtics',
            'cha': 'charlotte-hornets', 'chi': 'chicago-bulls', 'cle': 'cleveland-cavaliers',
            'dal': 'dallas-mavericks', 'den': 'denver-nuggets', 'det': 'detroit-pistons',
            'gs': 'golden-state-warriors', 'hou': 'houston-rockets', 'ind': 'indiana-pacers',
            'lac': 'los-angeles-clippers', 'lal': 'los-angeles-lakers', 'mem': 'memphis-grizzlies',
            'mia': 'miami-heat', 'mil': 'milwaukee-bucks', 'min': 'minnesota-timberwolves',
            'no': 'new-orleans-pelicans', 'ny': 'new-york-knicks', 'okc': 'oklahoma-city-thunder',
            'orl': 'orlando-magic', 'phi': 'philadelphia-76ers', 'phx': 'phoenix-suns',
            'por': 'portland-trail-blazers', 'sac': 'sacramento-kings', 'sa': 'san-antonio-spurs',
            'tor': 'toronto-raptors', 'utah': 'utah-jazz', 'wsh': 'washington-wizards'
        }
        
        full_team_name = team_name_map.get(espn_team_name)
        if not full_team_name:
            print(f"    ⚠️  Unknown full team name for {team_abbrev}")
            return []
        
        url = f"https://www.espn.com/nba/team/roster/_/name/{espn_team_name}/{full_team_name}"
        soup = self._get_page(url)
        
        if not soup:
            return []
        
        players = []
        
        try:
            # ESPN roster structure: Table with player data
            # Look for the roster table
            roster_table = soup.find('table', class_='Table')
            if not roster_table:
                # Try alternative table classes
                roster_table = soup.find('table')
            
            if roster_table:
                rows = roster_table.find('tbody').find_all('tr') if roster_table.find('tbody') else []
                
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) < 2:
                        continue
                    
                    # ESPN format: Name link, Position, Age, Height, Weight, etc.
                    name_cell = cells[0]
                    name_link = name_cell.find('a')
                    
                    if not name_link:
                        continue
                    
                    # Extract player name
                    player_name = name_link.get_text(strip=True)
                    
                    # Extract ESPN player ID from href (e.g., /nba/player/_/id/4066648/luka-doncic)
                    href = name_link.get('href', '')
                    espn_id_match = re.search(r'/id/(\d+)/', href)
                    espn_id = espn_id_match.group(1) if espn_id_match else None
                    
                    # Extract position (usually in second column)
                    position = cells[1].get_text(strip=True) if len(cells) > 1 else None
                    
                    # Extract height (usually 4th or 5th column)
                    height_str = None
                    for i, cell in enumerate(cells):
                        cell_text = cell.get_text(strip=True)
                        # Look for height format like "6-7" or "6'7\""
                        if re.match(r'\d+[\'-]\d+', cell_text) and not cell_text.startswith('$'):
                            height_str = cell_text
                            break
                    
                    # Extract weight
                    weight_str = None
                    for i, cell in enumerate(cells):
                        cell_text = cell.get_text(strip=True)
                        # Look for weight format (numbers with optional "lbs")
                        if re.match(r'^\d+\s*(lbs)?$', cell_text):
                            weight_str = cell_text.replace('lbs', '').strip()
                            break
                    
                    # Convert height to inches
                    height = None
                    if height_str:
                        # Handle formats: "6-7" or "6'7\"" or "6'7"
                        height_str = height_str.replace('"', '').replace("'", '-')
                        try:
                            parts = height_str.split('-')
                            if len(parts) == 2:
                                feet = int(parts[0])
                                inches = int(parts[1])
                                height = feet * 12 + inches
                        except:
                            pass
                    
                    # Convert weight to int
                    weight = None
                    if weight_str:
                        try:
                            weight = int(weight_str)
                        except:
                            pass
                    
                    players.append({
                        'name': player_name,
                        'position': position,
                        'height': height,
                        'weight': weight,
                        'espn_id': espn_id,
                        'team_abbrev': team_abbrev
                    })
        except Exception as e:
            print(f"    ⚠️  Error parsing roster for {team_abbrev}: {e}")
        
        return players
    
    def get_all_players(self) -> List[Dict]:
        """
        Scrape all NBA players from ESPN team rosters.
        
        Returns:
            List of player dictionaries from all teams
        """
        print("🏀 Scraping NBA players from ESPN...")
        print("=" * 60)
        
        teams = self.get_all_teams()
        print(f"Found {len(teams)} NBA teams")
        print()
        
        all_players = []
        
        for idx, team in enumerate(teams, 1):
            print(f"[{idx}/{len(teams)}] Scraping {team.abbreviation} ({team.name})...")
            players = self.scrape_team_roster(team.abbreviation)
            all_players.extend(players)
            print(f"    ✅ Found {len(players)} players")
            
            # Small delay between teams
            if idx < len(teams):
                time.sleep(0.5)
        
        print()
        print(f"✅ Total players scraped: {len(all_players)}")
        return all_players
    
    def find_team_by_abbreviation(self, abbreviation: str) -> Optional[Team]:
        """Find team by abbreviation."""
        return self.db.query(Team).filter(
            Team.abbreviation == abbreviation,
            Team.sport == 'NBA'
        ).first()
    
    def __del__(self):
        """Close database session if we created it."""
        if hasattr(self, 'db') and not hasattr(self, '_session_provided'):
            self.db.close()

