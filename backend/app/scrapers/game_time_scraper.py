"""
Game Time Scraper

Scrapes game times from NBA.com schedule pages.
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from typing import Optional, Dict
import time
import re


class GameTimeScraper:
    """Scrape game times from NBA.com."""
    
    def __init__(self, delay: float = 1.0):
        """
        Initialize scraper.
        
        Args:
            delay: Seconds to wait between requests
        """
        self.delay = delay
        self.last_request_time = 0
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def _rate_limit(self):
        """Enforce rate limiting."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        
        self.last_request_time = time.time()
    
    def scrape_game_times_for_date(self, game_date: date) -> Dict[str, str]:
        """
        Scrape game times for a specific date from NBA.com.
        
        Args:
            game_date: Date to scrape games for
            
        Returns:
            Dict mapping NBA game ID to game time (ISO format string)
        """
        self._rate_limit()
        
        # NBA.com schedule URL format: https://www.nba.com/schedule?date=YYYY-MM-DD
        url = f"https://www.nba.com/schedule?date={game_date.strftime('%Y-%m-%d')}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # NBA.com uses data attributes or specific classes for game times
            # This is a simplified parser - may need adjustment based on actual HTML structure
            game_times = {}
            
            # Look for game cards/containers
            # NBA.com structure may vary, so we'll try multiple approaches
            game_containers = soup.find_all(['div', 'section'], class_=re.compile(r'game|match|schedule', re.I))
            
            for container in game_containers:
                # Try to find game ID and time
                # This is a placeholder - actual implementation depends on NBA.com structure
                time_elem = container.find(['time', 'span', 'div'], class_=re.compile(r'time|start', re.I))
                if time_elem:
                    time_str = time_elem.get_text(strip=True)
                    # Try to parse time and convert to datetime
                    # Format might be "8:00 PM ET" or similar
                    try:
                        parsed_time = self._parse_time_string(time_str, game_date)
                        if parsed_time:
                            # Try to find game ID from data attributes or links
                            game_link = container.find('a', href=re.compile(r'/game/'))
                            if game_link:
                                game_id_match = re.search(r'/game/(\d+)', game_link.get('href', ''))
                                if game_id_match:
                                    game_id = game_id_match.group(1)
                                    game_times[game_id] = parsed_time.isoformat()
                    except Exception as e:
                        print(f"  ⚠️  Error parsing time '{time_str}': {e}")
                        continue
            
            # If the above doesn't work, try alternative approach
            # Look for JSON data embedded in the page
            scripts = soup.find_all('script', type='application/json')
            for script in scripts:
                try:
                    import json
                    data = json.loads(script.string)
                    # Navigate JSON structure to find game times
                    # This depends on NBA.com's actual JSON structure
                    if isinstance(data, dict):
                        games = data.get('games', []) or data.get('schedule', [])
                        for game in games:
                            if isinstance(game, dict):
                                game_id = str(game.get('gameId') or game.get('id', ''))
                                time_str = game.get('gameTime') or game.get('startTime') or game.get('time')
                                if game_id and time_str:
                                    try:
                                        parsed_time = self._parse_time_string(time_str, game_date)
                                        if parsed_time:
                                            game_times[game_id] = parsed_time.isoformat()
                                    except:
                                        pass
                except:
                    continue
            
            return game_times
            
        except Exception as e:
            print(f"❌ Error scraping game times from NBA.com for {game_date}: {e}")
            return {}
    
    def _parse_time_string(self, time_str: str, game_date: date) -> Optional[datetime]:
        """
        Parse time string to datetime.
        
        Handles formats like:
        - "8:00 PM ET"
        - "8:00 PM"
        - "20:00"
        - "8:00 PM CST"
        """
        time_str = time_str.strip().upper()
        
        # Remove timezone abbreviations
        timezone_map = {
            'ET': -5, 'EST': -5, 'EDT': -4,
            'CT': -6, 'CST': -6, 'CDT': -5,
            'MT': -7, 'MST': -7, 'MDT': -6,
            'PT': -8, 'PST': -8, 'PDT': -7
        }
        
        timezone_offset = 0
        for tz, offset in timezone_map.items():
            if tz in time_str:
                timezone_offset = offset
                time_str = time_str.replace(tz, '').strip()
                break
        
        # Try parsing with various formats
        formats = [
            '%I:%M %p',  # 8:00 PM
            '%H:%M',     # 20:00
            '%I %p',     # 8 PM
        ]
        
        for fmt in formats:
            try:
                parsed = datetime.strptime(time_str, fmt)
                # Combine with game date
                combined = datetime.combine(game_date, parsed.time())
                # Apply timezone offset (simplified - assumes UTC-5 for ET)
                # In production, use proper timezone handling
                return combined
            except ValueError:
                continue
        
        return None


def test_scraper():
    """Test the game time scraper."""
    scraper = GameTimeScraper()
    today = date.today()
    times = scraper.scrape_game_times_for_date(today)
    print(f"Found {len(times)} game times for {today}")
    for game_id, game_time in times.items():
        print(f"  Game {game_id}: {game_time}")


if __name__ == "__main__":
    test_scraper()


