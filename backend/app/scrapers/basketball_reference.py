"""
Basketball Reference Scraper

Scrapes box scores and game data from basketball-reference.com as a fallback
when NBA API is unavailable or unreliable.
"""
import time
import re
from typing import List, Dict, Optional
from datetime import date, datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup


class BasketballReferenceScraper:
    """Scraper for basketball-reference.com"""
    
    BASE_URL = "https://www.basketball-reference.com"
    
    # Team abbreviation mapping (Basketball Reference uses different abbreviations)
    TEAM_ABBREV_MAP = {
        'ATL': 'ATL', 'BOS': 'BOS', 'BKN': 'BRK', 'BRK': 'BRK',  # Brooklyn
        'CHA': 'CHO', 'CHO': 'CHO',  # Charlotte
        'CHI': 'CHI', 'CLE': 'CLE', 'DAL': 'DAL', 'DEN': 'DEN',
        'DET': 'DET', 'GSW': 'GSW', 'HOU': 'HOU', 'IND': 'IND',
        'LAC': 'LAC', 'LAL': 'LAL', 'MEM': 'MEM', 'MIA': 'MIA',
        'MIL': 'MIL', 'MIN': 'MIN', 'NOP': 'NOP', 'NOH': 'NOP',  # New Orleans
        'NYK': 'NYK', 'OKC': 'OKC', 'ORL': 'ORL', 'PHI': 'PHI',
        'PHX': 'PHO', 'PHO': 'PHO',  # Phoenix
        'POR': 'POR', 'SAC': 'SAC', 'SAS': 'SAS', 'TOR': 'TOR',
        'UTA': 'UTA', 'WAS': 'WAS'
    }
    
    def __init__(self, delay: float = 2.0):
        """
        Initialize scraper.
        
        Args:
            delay: Seconds to wait between requests (Basketball Reference recommends 2-3 seconds)
        """
        self.delay = delay
        self.last_request_time = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
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
        # Basketball Reference uses YYYYMMDD format
        url = f"{self.BASE_URL}/boxscores/?month={game_date.month}&day={game_date.day}&year={game_date.year}"
        
        soup = self._get_page(url)
        if not soup:
            print(f"    ⚠️  Could not fetch games page for {game_date}")
            return []
        
        games = []
        
        # Find all game links - Basketball Reference has links like /boxscores/202412280LAL.html
        game_links = soup.find_all('a', href=re.compile(r'/boxscores/\d+[A-Z]+\.html'))
        
        if not game_links:
            # Try alternative: look for score links
            game_links = soup.find_all('a', string=re.compile(r'\d+'))
            # Filter for box score links
            game_links = [link for link in soup.find_all('a') if link.get('href', '').startswith('/boxscores/')]
        
        for link in game_links:
            href = link.get('href')
            if not href:
                continue
            
            # Extract game ID from URL (e.g., /boxscores/202412280LAL.html)
            match = re.search(r'/boxscores/(\d+)([A-Z]+)\.html', href)
            if match:
                date_part = match.group(1)
                home_team_abbrev_br = match.group(2)
                
                # Convert Basketball Reference abbrev to our abbrev
                home_team_abbrev = self._convert_team_abbrev(home_team_abbrev_br)
                
                games.append({
                    'date': game_date,
                    'home_team_abbrev': home_team_abbrev,
                    'home_team_abbrev_br': home_team_abbrev_br,
                    'box_score_url': urljoin(self.BASE_URL, href)
                })
        
        return games
    
    def _convert_team_abbrev(self, br_abbrev: str) -> str:
        """Convert Basketball Reference abbreviation to our standard abbreviation."""
        # Reverse lookup
        reverse_map = {
            'BRK': 'BKN', 'CHO': 'CHA', 'NOP': 'NOP', 'PHO': 'PHX'
        }
        return reverse_map.get(br_abbrev, br_abbrev)
    
    def get_box_score(self, box_score_url: str, game_date: date) -> Optional[Dict]:
        """
        Get box score for a specific game.
        
        Args:
            box_score_url: Full URL to the box score page
            game_date: Date of the game
        
        Returns:
            Dictionary with player stats and team info, or None
        """
        soup = self._get_page(box_score_url)
        if not soup:
            print(f"    ⚠️  Could not fetch box score page")
            return None
        
        # Check if page exists (404 or no content)
        if soup.find('title') and '404' in soup.find('title').text:
            print(f"    ⚠️  Box score page not found (404)")
            return None
        
        try:
            # Find the two team sections (visitor and home)
            box_scores = soup.find_all('div', class_='table_wrapper')
            
            if len(box_scores) < 2:
                print(f"  ⚠️  Could not find both team box scores")
                return None
            
            # Get team names
            scorebox = soup.find('div', class_='scorebox')
            if not scorebox:
                return None
            
            # Extract team names from scorebox
            team_links = scorebox.find_all('a', href=re.compile(r'/teams/'))
            if len(team_links) < 2:
                return None
            
            visitor_team_abbrev = self._extract_team_abbrev(team_links[0].get('href', ''))
            home_team_abbrev = self._extract_team_abbrev(team_links[1].get('href', ''))
            
            # Get scores
            scores = scorebox.find_all('div', class_='score')
            visitor_score = None
            home_score = None
            if len(scores) >= 2:
                try:
                    visitor_score = int(scores[0].text.strip())
                    home_score = int(scores[1].text.strip())
                except:
                    pass
            
            # Parse player stats from both teams
            player_stats = []
            
            # Find all basic game tables (one per team)
            # Basketball Reference uses IDs like: box-chi-basic, box-atl-basic
            basic_tables = soup.find_all('table', id=re.compile(r'box-[a-z]+-basic'))
            
            # Debug: print what we found
            if not basic_tables:
                # Try alternative pattern
                basic_tables = soup.find_all('table', id=re.compile(r'box-.*-basic'))
            
            if len(basic_tables) >= 2:
                # Visitor team stats (first table)
                visitor_table = basic_tables[0]
                visitor_stats = self._parse_player_stats_table(visitor_table, visitor_team_abbrev, home_team_abbrev, False)
                player_stats.extend(visitor_stats)
                
                # Home team stats (second table)
                home_table = basic_tables[1]
                home_stats = self._parse_player_stats_table(home_table, home_team_abbrev, visitor_team_abbrev, True)
                player_stats.extend(home_stats)
            elif len(basic_tables) == 1:
                # Only one table found, try to determine which team
                # Usually visitor is first, but let's check the table ID
                table_id = basic_tables[0].get('id', '')
                if visitor_team_abbrev.lower() in table_id:
                    visitor_stats = self._parse_player_stats_table(basic_tables[0], visitor_team_abbrev, home_team_abbrev, False)
                    player_stats.extend(visitor_stats)
                else:
                    home_stats = self._parse_player_stats_table(basic_tables[0], home_team_abbrev, visitor_team_abbrev, True)
                    player_stats.extend(home_stats)
            else:
                # Fallback: try using the table_wrapper divs
                if len(box_scores) >= 2:
                    visitor_table = box_scores[0].find('table', id=re.compile(r'box-.*-basic'))
                    if visitor_table:
                        visitor_stats = self._parse_player_stats_table(visitor_table, visitor_team_abbrev, home_team_abbrev, False)
                        player_stats.extend(visitor_stats)
                    
                    home_table = box_scores[1].find('table', id=re.compile(r'box-.*-basic'))
                    if home_table:
                        home_stats = self._parse_player_stats_table(home_table, home_team_abbrev, visitor_team_abbrev, True)
                        player_stats.extend(home_stats)
            
            return {
                'player_stats': player_stats,
                'visitor_team': visitor_team_abbrev,
                'home_team': home_team_abbrev,
                'visitor_score': visitor_score,
                'home_score': home_score,
                'game_date': game_date
            }
            
        except Exception as e:
            print(f"  ❌ Error parsing box score: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_team_abbrev(self, team_url: str) -> str:
        """Extract team abbreviation from Basketball Reference team URL."""
        match = re.search(r'/teams/([A-Z]+)/', team_url)
        if match:
            br_abbrev = match.group(1)
            return self._convert_team_abbrev(br_abbrev)
        return ''
    
    def _parse_player_stats_table(self, table, team_abbrev: str, opponent_abbrev: str, is_home: bool) -> List[Dict]:
        """Parse player stats from a box score table."""
        stats = []
        
        # Find the tbody
        tbody = table.find('tbody')
        if not tbody:
            print(f"    ⚠️  No tbody found in table")
            return stats
        
        rows = tbody.find_all('tr')
        
        for row in rows:
            # Skip team totals row and header rows
            row_class = row.get('class', [])
            if 'thead' in row_class or 'over_header' in row_class:
                continue
            
            # Get player name and link
            name_cell = row.find('th', {'data-stat': 'player'})
            if not name_cell:
                # Try alternative: th with class
                name_cell = row.find('th', class_=re.compile(r'.*'))
                if not name_cell:
                    continue
            
            player_link = name_cell.find('a')
            if not player_link:
                # Skip team totals (they don't have links)
                continue
            
            player_name = player_link.text.strip()
            
            if not player_name:
                continue
            
            # Get all stat cells
            cells = row.find_all('td')
            
            # Helper to get stat value
            def get_stat(stat_name: str, default=0):
                for cell in cells:
                    if cell.get('data-stat') == stat_name:
                        text = cell.text.strip()
                        if text == '':
                            return default
                        try:
                            # Handle minutes (e.g., "24:30" -> 24.5)
                            if stat_name == 'mp':
                                parts = text.split(':')
                                if len(parts) == 2:
                                    return int(parts[0]) + int(parts[1]) / 60.0
                                return float(text)
                            return int(float(text))
                        except:
                            return default
                return default
            
            stat_dict = {
                'PLAYER_NAME': player_name,
                'TEAM_ABBREVIATION': team_abbrev,
                'MIN': get_stat('mp', 0),
                'PTS': get_stat('pts', 0),
                'REB': get_stat('trb', 0),
                'OREB': get_stat('orb', 0),
                'DREB': get_stat('drb', 0),
                'AST': get_stat('ast', 0),
                'STL': get_stat('stl', 0),
                'BLK': get_stat('blk', 0),
                'TOV': get_stat('tov', 0),
                'PF': get_stat('pf', 0),
                'FGM': get_stat('fg', 0),
                'FGA': get_stat('fga', 0),
                'FG3M': get_stat('fg3', 0),
                'FG3A': get_stat('fg3a', 0),
                'FTM': get_stat('ft', 0),
                'FTA': get_stat('fta', 0),
                'PLUS_MINUS': get_stat('plus_minus', 0),
                'IS_HOME': is_home,
                'OPPONENT_ABBREV': opponent_abbrev
            }
            
            stats.append(stat_dict)
        
        return stats
    
    def get_box_score_by_date_and_teams(self, game_date: date, home_team_abbrev: str) -> Optional[Dict]:
        """
        Get box score by finding the game URL first.
        
        Args:
            game_date: Date of the game
            home_team_abbrev: Home team abbreviation
        
        Returns:
            Box score dictionary or None
        """
        # First, try to get all games for the date and find the matching one
        # This is more reliable than constructing the URL directly
        games = self.get_games_for_date(game_date)
        
        if not games:
            print(f"    ⚠️  No games found for {game_date} on Basketball Reference")
            return None
        
        print(f"    🔍 Found {len(games)} games for {game_date}, looking for {home_team_abbrev}...")
        
        # Find game with matching home team
        for game in games:
            if game['home_team_abbrev'] == home_team_abbrev:
                print(f"    ✅ Found matching game: {game['box_score_url']}")
                return self.get_box_score(game['box_score_url'], game_date)
        
        # If no exact match, try with Basketball Reference abbreviation
        br_abbrev_map = {
            'BKN': 'BRK', 'CHA': 'CHO', 'PHX': 'PHO', 'NOP': 'NOP', 'NOH': 'NOP'
        }
        br_home_abbrev = br_abbrev_map.get(home_team_abbrev, home_team_abbrev)
        
        for game in games:
            if game.get('home_team_abbrev_br') == br_home_abbrev:
                print(f"    ✅ Found matching game (BR abbrev): {game['box_score_url']}")
                return self.get_box_score(game['box_score_url'], game_date)
        
        # Last resort: try constructing URL directly
        date_str = game_date.strftime("%Y%m%d")
        url = f"{self.BASE_URL}/boxscores/{date_str}0{br_home_abbrev}.html"
        print(f"    🔍 Trying direct URL: {url}")
        return self.get_box_score(url, game_date)


def test_scraper():
    """Test the Basketball Reference scraper."""
    scraper = BasketballReferenceScraper()
    
    # Test getting yesterday's games
    yesterday = date.today() - timedelta(days=1)
    print(f"Testing scraper for {yesterday}...")
    
    games = scraper.get_games_for_date(yesterday)
    print(f"Found {len(games)} games")
    
    if games:
        # Test getting box score for first game
        first_game = games[0]
        print(f"\nTesting box score for: {first_game['home_team_abbrev']}")
        box_score = scraper.get_box_score(first_game['box_score_url'], yesterday)
        
        if box_score:
            print(f"✅ Successfully scraped box score!")
            print(f"   Teams: {box_score['visitor_team']} @ {box_score['home_team']}")
            print(f"   Score: {box_score['visitor_score']} - {box_score['home_score']}")
            print(f"   Players: {len(box_score['player_stats'])}")
            if box_score['player_stats']:
                first_player = box_score['player_stats'][0]
                print(f"   Sample player: {first_player['PLAYER_NAME']} - {first_player['PTS']} pts, {first_player['REB']} reb, {first_player['AST']} ast")


if __name__ == "__main__":
    from datetime import timedelta
    test_scraper()

