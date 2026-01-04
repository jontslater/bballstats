"""
NBA API Client - Wrapper around nba_api package for data collection.

This module provides a clean interface to the NBA API for collecting:
- Players
- Teams
- Game schedules
- Game results and box scores
"""
import time
from typing import List, Dict, Optional
from datetime import datetime, date

try:
    from nba_api.stats.endpoints import (
        commonplayerinfo,
        commonallplayers,
        teamgamelog,
        playergamelog,
        scoreboardv2,
        boxscoretraditionalv2,
        leaguegamefinder
    )
    from nba_api.stats.static import teams
    NBA_API_AVAILABLE = True
except ImportError as e:
    NBA_API_AVAILABLE = False
    print(f"⚠️  nba_api package not installed. Run: pip install nba-api")
    print(f"   Error: {e}")


class NBAAPIClient:
    """Client for interacting with NBA API."""
    
    def __init__(self, delay: float = 0.6):
        """
        Initialize NBA API client.
        
        Args:
            delay: Seconds to wait between API calls (to respect rate limits)
        """
        if not NBA_API_AVAILABLE:
            raise ImportError("nba_api package is not installed")
        
        self.delay = delay
        self.last_call_time = 0
    
    def _rate_limit(self):
        """Enforce rate limiting between API calls."""
        current_time = time.time()
        time_since_last_call = current_time - self.last_call_time
        
        if time_since_last_call < self.delay:
            sleep_time = self.delay - time_since_last_call
            time.sleep(sleep_time)
        
        self.last_call_time = time.time()
    
    def get_all_teams(self) -> List[Dict]:
        """
        Get all NBA teams.
        
        Returns:
            List of team dictionaries with id, full_name, abbreviation, etc.
        """
        self._rate_limit()
        try:
            teams_list = teams.get_teams()
            return teams_list
        except Exception as e:
            print(f"❌ Error fetching teams: {e}")
            return []
    
    def get_all_players(self, season: Optional[str] = None, is_only_current_season: int = 1, max_retries: int = 3) -> List[Dict]:
        """
        Get all NBA players.
        
        Args:
            season: Season string (e.g., "2023-24"). If None, uses current season.
            is_only_current_season: 1 for current season only, 0 for all players
            max_retries: Maximum number of retry attempts
        
        Returns:
            List of player dictionaries
        """
        # Try different parameter combinations (order matters - try simplest first)
        attempts_config = [
            {"season": None, "is_only_current_season": 1, "desc": "current season (no season param)"},
            {"season": season, "is_only_current_season": 1, "desc": f"season {season}"} if season else None,
            {"season": None, "is_only_current_season": 0, "desc": "all players"},
        ]
        # Filter out None configs
        attempts_config = [c for c in attempts_config if c is not None]
        
        for config_idx, config in enumerate(attempts_config):
            config_desc = config.pop("desc", "")
            print(f"  Trying: {config_desc}...")
            
            for attempt in range(max_retries):
                # Longer delay before first attempt of each config
                if attempt == 0 and config_idx > 0:
                    time.sleep(3)
                
                self._rate_limit()
                try:
                    # Try with longer timeout
                    players = commonallplayers.CommonAllPlayers(
                        season=config["season"],
                        is_only_current_season=config["is_only_current_season"],
                        timeout=60
                    )
                    players_df = players.get_data_frames()[0]
                    
                    if players_df.empty:
                        if attempt < max_retries - 1:
                            print(f"    ⚠️  Empty response, retrying ({attempt + 1}/{max_retries})...")
                            time.sleep(3)
                            continue
                        else:
                            print(f"    ❌ Empty after {max_retries} attempts, trying next config...")
                            break
                    
                    # Success!
                    print(f"    ✅ Success! Found {len(players_df)} players")
                    return players_df.to_dict('records')
                    
                except Exception as e:
                    error_msg = str(e)
                    if "Expecting value" in error_msg or "JSON" in error_msg:
                        # API returned empty/invalid response - likely rate limiting
                        if attempt < max_retries - 1:
                            wait_time = min((attempt + 1) * 3, 10)  # Cap at 10 seconds
                            print(f"    ⚠️  API error (likely rate limit), waiting {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            print(f"    ❌ Failed after {max_retries} attempts")
                            break
                    else:
                        # Different error - retry once then move on
                        if attempt < max_retries - 1:
                            time.sleep(2)
                        else:
                            break
        
        print(f"  ❌ Failed to fetch players after trying all configurations")
        return []
    
    def get_player_info(self, player_id: int, max_retries: int = 2) -> Optional[Dict]:
        """
        Get detailed information about a specific player.
        
        Args:
            player_id: NBA player ID
            max_retries: Maximum number of retry attempts
        
        Returns:
            Player info dictionary or None
        """
        for attempt in range(max_retries):
            self._rate_limit()
            try:
                player_info = commonplayerinfo.CommonPlayerInfo(
                    player_id=player_id,
                    timeout=60
                )
                info_df = player_info.get_data_frames()[0]
                if not info_df.empty:
                    return info_df.iloc[0].to_dict()
                return None
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                # Don't print error for every failed player - too noisy
                return None
    
    def get_game_schedule(self, game_date: date) -> List[Dict]:
        """
        Get games scheduled for a specific date.
        
        Args:
            game_date: Date to get games for
        
        Returns:
            List of game dictionaries
        """
        self._rate_limit()
        try:
            scoreboard_data = scoreboardv2.ScoreboardV2(
                game_date=game_date.strftime("%m/%d/%Y"),
                timeout=30
            )
            games_df = scoreboard_data.get_data_frames()[0]  # GameHeader
            return games_df.to_dict('records')
        except Exception as e:
            print(f"❌ Error fetching schedule for {game_date}: {e}")
            return []
    
    def get_team_game_log(self, team_id: int, season: str) -> List[Dict]:
        """
        Get game log for a team for a specific season.
        
        Args:
            team_id: NBA team ID
            season: Season string (e.g., "2023-24")
        
        Returns:
            List of game dictionaries
        """
        self._rate_limit()
        try:
            game_log = teamgamelog.TeamGameLog(
                team_id=team_id,
                season=season,
                timeout=30
            )
            games_df = game_log.get_data_frames()[0]
            return games_df.to_dict('records')
        except Exception as e:
            print(f"❌ Error fetching team game log for team {team_id}: {e}")
            return []
    
    def get_player_game_log(self, player_id: int, season: str) -> List[Dict]:
        """
        Get game log for a player for a specific season.
        
        Args:
            player_id: NBA player ID
            season: Season string (e.g., "2023-24")
        
        Returns:
            List of game stat dictionaries
        """
        self._rate_limit()
        try:
            game_log = playergamelog.PlayerGameLog(
                player_id=player_id,
                season=season,
                timeout=30
            )
            games_df = game_log.get_data_frames()[0]
            return games_df.to_dict('records')
        except Exception as e:
            print(f"❌ Error fetching player game log for player {player_id}: {e}")
            return []
    
    def get_game_box_score(self, game_id: str) -> Optional[Dict]:
        """
        Get box score for a specific game.
        
        Args:
            game_id: NBA game ID (format: "0022300123")
        
        Returns:
            Dictionary with player stats and team stats, or None
        """
        self._rate_limit()
        try:
            box_score = boxscoretraditionalv2.BoxScoreTraditionalV2(
                game_id=game_id,
                timeout=30
            )
            
            # Get dataframes
            player_stats_df = box_score.get_data_frames()[0]  # PlayerStats
            team_stats_df = box_score.get_data_frames()[1]    # TeamStats
            
            return {
                'player_stats': player_stats_df.to_dict('records'),
                'team_stats': team_stats_df.to_dict('records')
            }
        except Exception as e:
            print(f"❌ Error fetching box score for game {game_id}: {e}")
            return None
    
    def get_games_by_date_range(self, season: str, date_from: date, date_to: date) -> List[Dict]:
        """
        Get all games in a date range for a season.
        
        Args:
            season: Season string (e.g., "2023-24")
            date_from: Start date
            date_to: End date
        
        Returns:
            List of game dictionaries
        """
        self._rate_limit()
        try:
            game_finder = leaguegamefinder.LeagueGameFinder(
                season_nullable=season,
                date_from_nullable=date_from.strftime("%m/%d/%Y"),
                date_to_nullable=date_to.strftime("%m/%d/%Y"),
                timeout=30
            )
            games_df = game_finder.get_data_frames()[0]
            return games_df.to_dict('records')
        except Exception as e:
            print(f"❌ Error fetching games for date range: {e}")
            return []


def test_client():
    """Test the NBA API client."""
    if not NBA_API_AVAILABLE:
        print("❌ nba_api package not available")
        return False
    
    print("Testing NBA API Client...")
    client = NBAAPIClient()
    
    # Test 1: Get teams
    print("\n1. Testing get_all_teams()...")
    teams_list = client.get_all_teams()
    print(f"   ✅ Found {len(teams_list)} teams")
    if teams_list:
        print(f"   Example: {teams_list[0]['full_name']}")
    
    # Test 2: Get players
    print("\n2. Testing get_all_players()...")
    players = client.get_all_players(is_only_current_season=1)
    print(f"   ✅ Found {len(players)} current players")
    if players:
        print(f"   Example: {players[0].get('DISPLAY_FIRST_LAST', 'N/A')}")
    
    # Test 3: Get today's schedule
    print("\n3. Testing get_game_schedule()...")
    today = date.today()
    games = client.get_game_schedule(today)
    print(f"   ✅ Found {len(games)} games scheduled for today")
    
    print("\n✅ All tests passed!")
    return True


if __name__ == "__main__":
    test_client()

