"""
ESPN NFL API Client

Provides NFL schedule and game data via ESPN's public API.
Primary data source for NFL schedules to avoid HTTP 403 from Pro Football Reference.
"""

import requests
from datetime import date, datetime
from typing import List, Dict, Optional
import time


class ESPNNFLClient:
    """Client for ESPN NFL API."""

    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
    
    def __init__(self, delay: float = 0.5):
        """
        Initialize ESPN NFL client.
        
        Args:
            delay: Seconds to wait between API calls (rate limiting)
        """
        self.delay = delay
        self.last_call_time = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def _rate_limit(self):
        """Simple rate limiting to be respectful to ESPN's API."""
        current_time = time.time()
        time_since_last = current_time - self.last_call_time
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        self.last_call_time = time.time()

    def get_scoreboard(self, game_date: Optional[date] = None) -> Dict:
        """
        Get NFL scoreboard for a specific date.
        
        Args:
            game_date: Date to get scoreboard for (defaults to today)
            
        Returns:
            Dict containing scoreboard data
        """
        self._rate_limit()
        
        url = f"{self.BASE_URL}/scoreboard"
        params = {}
        if game_date:
            params['dates'] = game_date.strftime('%Y%m%d')
        
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"⚠️ ESPN API error: {e}")
            return {}

    def get_week_schedule(self, season: int, week: int, season_type: int = 2) -> List[Dict]:
        """
        Get NFL schedule for a specific week.
        
        Args:
            season: Year (e.g., 2024, 2025)
            week: Week number (1-18 for regular season, 19-22 for playoffs)
            season_type: 1=preseason, 2=regular season, 3=playoffs, 4=pro bowl
            
        Returns:
            List of game dictionaries with standardized fields
        """
        self._rate_limit()
        
        url = f"{self.BASE_URL}/scoreboard"
        params = {
            'seasontype': season_type,
            'week': week,
            'season': season
        }
        
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            games = []
            for event in data.get('events', []):
                game = self._parse_event(event)
                if game:
                    games.append(game)
            
            return games
            
        except requests.RequestException as e:
            print(f"⚠️ ESPN API error for week {week}: {e}")
            return []

    def get_season_schedule(self, season: int, season_type: int = 2) -> List[Dict]:
        """
        Get full NFL season schedule.
        
        Args:
            season: Year (e.g., 2024, 2025)
            season_type: 1=preseason, 2=regular season, 3=playoffs
            
        Returns:
            List of all games for the season
        """
        all_games = []
        
        # Regular season: 18 weeks
        max_week = 18 if season_type == 2 else (4 if season_type == 1 else 5)
        
        for week in range(1, max_week + 1):
            print(f"  Fetching week {week}/{max_week}...")
            games = self.get_week_schedule(season, week, season_type)
            all_games.extend(games)
            
        return all_games

    def _parse_event(self, event: Dict) -> Optional[Dict]:
        """
        Parse ESPN event data into standardized game format.
        
        Returns:
            Dict with fields:
                - espn_game_id: ESPN game ID
                - game_date: Date object
                - game_time: Datetime object (if available)
                - home_team_espn_id: ESPN team ID for home team
                - away_team_espn_id: ESPN team ID for away team
                - home_team_abbrev: Team abbreviation
                - away_team_abbrev: Team abbreviation
                - home_team_name: Full team name
                - away_team_name: Full team name
                - status: Game status (scheduled, in_progress, final)
                - home_score: Score (if available)
                - away_score: Score (if available)
        """
        try:
            competitions = event.get('competitions', [])
            if not competitions:
                return None
            
            comp = competitions[0]
            competitors = comp.get('competitors', [])
            if len(competitors) < 2:
                return None
            
            # Find home and away teams
            home_team = next((c for c in competitors if c.get('homeAway') == 'home'), None)
            away_team = next((c for c in competitors if c.get('homeAway') == 'away'), None)
            
            if not home_team or not away_team:
                return None
            
            # Parse date/time
            date_str = event.get('date', '')
            game_datetime = None
            game_date = None
            if date_str:
                try:
                    game_datetime = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    game_date = game_datetime.date()
                except:
                    pass
            
            # Parse status
            status_type = event.get('status', {}).get('type', {}).get('name', '')
            status_map = {
                'STATUS_SCHEDULED': 'scheduled',
                'STATUS_IN_PROGRESS': 'in_progress',
                'STATUS_FINAL': 'final',
                'STATUS_HALFTIME': 'in_progress',
                'STATUS_END_PERIOD': 'in_progress',
                'STATUS_POSTPONED': 'postponed',
                'STATUS_CANCELED': 'cancelled'
            }
            status = status_map.get(status_type, 'scheduled')
            
            # Extract scores (if available)
            home_score = home_team.get('score')
            away_score = away_team.get('score')
            
            return {
                'espn_game_id': event.get('id', ''),
                'game_date': game_date,
                'game_time': game_datetime,
                'home_team_espn_id': home_team.get('team', {}).get('id', ''),
                'away_team_espn_id': away_team.get('team', {}).get('id', ''),
                'home_team_abbrev': home_team.get('team', {}).get('abbreviation', ''),
                'away_team_abbrev': away_team.get('team', {}).get('abbreviation', ''),
                'home_team_name': home_team.get('team', {}).get('displayName', ''),
                'away_team_name': away_team.get('team', {}).get('displayName', ''),
                'status': status,
                'home_score': int(home_score) if home_score is not None else None,
                'away_score': int(away_score) if away_score is not None else None,
            }
            
        except Exception as e:
            print(f"⚠️ Error parsing ESPN event: {e}")
            return None

    def map_espn_abbrev_to_nfl(self, espn_abbrev: str) -> str:
        """
        Map ESPN team abbreviation to our NFL team abbreviation.
        Most are identical, but handle any edge cases.
        
        Args:
            espn_abbrev: ESPN team abbreviation
            
        Returns:
            Our internal NFL team abbreviation
        """
        # ESPN uses standard NFL abbreviations
        # Handle any special cases here if needed
        mapping = {
            'WSH': 'WAS',  # Washington changed name
            # Add other mappings as discovered
        }
        return mapping.get(espn_abbrev.upper(), espn_abbrev.upper())
